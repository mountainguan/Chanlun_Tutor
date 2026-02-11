import os
import json
import time
import datetime
import pandas as pd
import akshare as ak
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.social_security_fund import SocialSecurityFund
from utils.fund_radar import FundRadar
from utils.simulator_logic import calculate_rsi, calculate_bollinger_bands


class NationalTeamSelector:
    THS_INDUSTRIES = {
        'IT服务', '专用设备', '中药', '互联网电商', '保险', '元件', '光伏设备', '光学光电子', '公路铁路运输', 
        '其他电子', '其他电源设备', '其他社会服务', '养殖业', '军工电子', '军工装备', '农产品加工', '农化制品', 
        '包装印刷', '化学制品', '化学制药', '化学原料', '化学纤维', '医疗器械', '医疗服务', '医药商业', '半导体', 
        '厨卫电器', '塑料制品', '多元金融', '家居用品', '小家电', '小金属', '工业金属', '工程机械', '建筑材料', 
        '建筑装饰', '影视院线', '房地产', '教育', '文化传媒', '旅游及酒店', '服装家纺', '机场航运', '橡胶制品', 
        '汽车整车', '汽车服务及其他', '汽车零部件', '油气开采及服务', '消费电子', '港口航运', '游戏', '煤炭开采加工', 
        '燃气', '物流', '环保设备', '环境治理', '生物制品', '电力', '电子化学品', '电机', '电池', '电网设备', 
        '白色家电', '白酒', '石油加工贸易', '种植业与林业', '纺织制造', '综合', '美容护理', '能源金属', '自动化设备', 
        '计算机设备', '证券', '贵金属', '贸易', '轨交设备', '软件开发', '通信服务', '通信设备', '通用设备', '造纸', 
        '金属新材料', '钢铁', '银行', '零售', '非金属材料', '风电设备', '食品加工制造', '饮料制造', '黑色家电'
    }

    # 手动映射表：EM行业名称 -> 同花顺行业名称
    EM_TO_THS_MAP = {
        '贸易行业': '贸易',
        '有色金属': '工业金属', # 或 小金属/能源金属/贵金属，需模糊匹配
        '食品饮料': '食品加工制造', # 或 饮料制造
        '农牧饲渔': '养殖业', # 或 种植业与林业
        '医药制造': '化学制药', # 或 中药/生物制品
        '电子元件': '元件',
        '通信行业': '通信设备',
        '家电行业': '白色家电',
        '纺织服装': '纺织制造', # 或 服装家纺
        '旅游酒店': '旅游及酒店',
        '医疗行业': '医疗服务', # 或 医疗器械
        '公用事业': '电力', # 粗略映射
        '酿酒行业': '白酒', # 或 饮料制造
        '石油行业': '石油加工贸易', # 或 油气开采
        '化工行业': '化学制品',
        '工程建设': '建筑装饰',
        '交运设备': '轨交设备',
        '贵金属': '贵金属',
        '钢铁行业': '钢铁',
        '煤炭行业': '煤炭开采加工',
        '玻璃玻纤': '建筑材料',
        '化肥行业': '农化制品',
        '船舶制造': '军工装备', # 近似
        '航天航空': '军工装备',
        '文化传媒': '文化传媒',
        '互联网服务': 'IT服务',
        '软件开发': '软件开发',
        '游戏': '游戏',
        '计算机设备': '计算机设备',
        '半导体': '半导体',
        '消费电子': '消费电子',
        '光学光电子': '光学光电子',
        '电池': '电池',
        '光伏设备': '光伏设备',
        '风电设备': '风电设备',
        '电网设备': '电网设备',
        # CSRC 行业映射 (fallback)
        '货币金融服务': '银行',
        '资本市场服务': '证券',
        '保险业': '保险',
        '酒、饮料和精制茶制造业': '饮料制造',
        '医药制造业': '化学制药',
        '汽车制造业': '汽车整车',
        '计算机、通信和其他电子设备制造业': '通信设备',
        '软件和信息技术服务业': '软件开发',
        '专用设备制造业': '专用设备',
        '通用设备制造业': '通用设备',
        '电气机械和器材制造业': '电网设备',
        '化学原料和化学制品制造业': '化学制品',
        '有色金属冶炼和压延加工业': '工业金属',
        '非金属矿物制品业': '建筑材料',
        '黑色金属冶炼和压延加工业': '钢铁',
        '煤炭开采和洗选业': '煤炭开采加工',
        '石油和天然气开采业': '油气开采及服务',
        '农副食品加工业': '农产品加工',
        '食品制造业': '食品加工制造',
    }

    def __init__(self, data_dir=None, cache_ttl=None):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.data_dir = data_dir if data_dir else os.path.join(base_dir, 'data')
        self.industry_cache_file = os.path.join(self.data_dir, 'stock_industry_cache.json')
        self.ma_cache_file = os.path.join(self.data_dir, 'stock_ma_cache.json')
        # 如果未指定 ttl，则默认为极大值（约10年），实现“永久缓存”
        self.cache_ttl = cache_ttl if cache_ttl is not None else 3600 * 24 * 365 * 10
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _load_cache(self, file_path):
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self, file_path, data):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _is_fresh(self, ts):
        try:
            return time.time() - float(ts) < self.cache_ttl
        except Exception:
            return False

    def _normalize_industry(self, name):
        if not name:
            return ''
        val = str(name).strip()
        for suffix in ['行业', '概念', '板块']:
            if val.endswith(suffix):
                val = val[: -len(suffix)]
        return val

    def _industry_from_info(self, df):
        if df is None or df.empty:
            return None
        try:
            info = {row['item']: row['value'] for row in df.to_dict('records')}
        except Exception:
            return None
        for key in ['所属行业', '行业', '行业板块', '行业分类', '概念板块']:
            if key in info and info[key]:
                return str(info[key]).strip()
        return None

    def _map_to_ths(self, industry_name):
        """将任意行业名称映射到同花顺行业"""
        if not industry_name:
            return ''
        
        name = str(industry_name).strip()
        
        # 1. 直接匹配
        if name in self.THS_INDUSTRIES:
            return name
            
        # 2. 查表映射
        if name in self.EM_TO_THS_MAP:
            return self.EM_TO_THS_MAP[name]
            
        # 3. 尝试去除后缀匹配 (e.g. "XX行业" -> "XX")
        norm_name = self._normalize_industry(name)
        if norm_name in self.THS_INDUSTRIES:
            return norm_name
            
        # 4. 模糊包含匹配
        # 如果 name 是 THS 中的某个行业的子集，或反之
        for ths_ind in self.THS_INDUSTRIES:
            if norm_name in ths_ind or ths_ind in norm_name:
                return ths_ind
                
        # 5. 无法映射，返回带星号的原名
        return f"*{name}"

    def _fetch_industry(self, code):
        # 1. 尝试 EM 接口
        for i in range(2):
            try:
                df = ak.stock_individual_info_em(symbol=code)
                res = self._industry_from_info(df)
                if res:
                    return self._map_to_ths(res)
            except Exception:
                time.sleep(0.5)
        
        # 2. 尝试 CNINFO 接口 (作为备用)
        try:
            df = ak.stock_profile_cninfo(symbol=code)
            if df is not None and not df.empty:
                # CNINFO 返回 '所属行业' 列
                # 数据可能是单行 DataFrame
                if '所属行业' in df.columns:
                    ind = df.iloc[0]['所属行业']
                    if ind:
                        return self._map_to_ths(ind)
        except Exception:
            pass
            
        return None

    def get_stock_industry_map(self, codes, force_update=False, progress_callback=None):
        cache = self._load_cache(self.industry_cache_file)
        result = {}
        missing = []
        for code in codes:
            cached = cache.get(code)
            if not force_update and cached and self._is_fresh(cached.get('timestamp')):
                if cached.get('industry'):
                    result[code] = cached.get('industry')
                continue
            missing.append(code)
        
        if missing:
            total = len(missing)
            completed = 0
            if progress_callback:
                progress_callback(0, total, "开始获取行业数据...")
                
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_code = {executor.submit(self._fetch_industry, code): code for code in missing}
                for future in as_completed(future_to_code):
                    code = future_to_code[future]
                    try:
                        industry = future.result(timeout=10)
                    except Exception:
                        industry = None
                    
                    industry = industry if industry else ''
                    cache[code] = {'industry': industry, 'timestamp': time.time()}
                    if industry:
                        result[code] = industry
                    
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total, f"获取行业数据: {completed}/{total}")
                        
            self._save_cache(self.industry_cache_file, cache)
        return result

    def _calc_ma(self, df):
        if df is None or df.empty:
            return None
        
        # 统一日期列名
        date_col = None
        for col in ['日期', 'date']:
            if col in df.columns:
                date_col = col
                break
        
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col)
            
        close_col = None
        for col in ['收盘', '收盘价', 'close']:
            if col in df.columns:
                close_col = col
                break
        if not close_col:
            return None
        closes = pd.to_numeric(df[close_col], errors='coerce').dropna()
        if closes.empty:
            return None
        last_price = float(closes.iloc[-1])
        ma5 = float(closes.tail(5).mean()) if len(closes) >= 5 else last_price
        ma10 = float(closes.tail(10).mean()) if len(closes) >= 10 else ma5
        ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else ma10
        
        # Calculate RSI
        rsi_values = calculate_rsi(closes.tolist(), period=14)
        rsi = float(rsi_values[-1]) if rsi_values else 50.0
        
        # Calculate Bollinger Bands
        bb = calculate_bollinger_bands(closes.tolist(), period=20, num_std=2)
        bb_upper = float(bb['upper'][-1]) if bb['upper'] else last_price
        bb_middle = float(bb['middle'][-1]) if bb['middle'] else last_price
        bb_lower = float(bb['lower'][-1]) if bb['lower'] else last_price
        
        return {
            'price': last_price, 
            'ma5': ma5, 
            'ma10': ma10, 
            'ma20': ma20,
            'rsi': rsi,
            'bb_upper': bb_upper,
            'bb_middle': bb_middle,
            'bb_lower': bb_lower
        }

    def _fetch_ma(self, code):
        end_dt = datetime.date.today()
        start_dt = end_dt - datetime.timedelta(days=120) # 增加到120天以确保足够的计算数据

        
        # 1. 尝试使用新浪接口（增加重试机制）
        for _ in range(3):
            try:
                symbol = code
                if code.startswith('6'):
                    symbol = 'sh' + code
                elif code.startswith('8') or code.startswith('4'):
                    symbol = 'bj' + code
                else:
                    symbol = 'sz' + code
                    
                df = ak.stock_zh_a_daily(
                    symbol=symbol,
                    start_date=start_dt.strftime('%Y%m%d'),
                    end_date=end_dt.strftime('%Y%m%d'),
                    adjust="qfq"
                )
                res = self._calc_ma(df)
                if res:
                    return res
            except Exception:
                time.sleep(0.5)

        # 2. 如果历史行情失败，尝试获取实时行情作为兜底（至少有最新价）
        try:
            df = ak.stock_zh_a_spot_em()
            # 过滤出当前股票
            row = df[df['代码'] == code]
            if not row.empty:
                price = row.iloc[0]['最新价']
                try:
                    price = float(price)
                    return {
                        'price': price, 
                        'ma5': None, 'ma10': None, 'ma20': None,
                        'rsi': None, 'bb_upper': None, 'bb_middle': None, 'bb_lower': None
                    }
                except:
                    pass
        except Exception:
            pass
            
        return None

    def get_stock_ma_map(self, codes, force_update=False, progress_callback=None):
        cache = self._load_cache(self.ma_cache_file)
        result = {}
        missing = []
        for code in codes:
            cached = cache.get(code)
            if not force_update and cached and self._is_fresh(cached.get('timestamp')):
                if cached.get('price') is not None:
                    result[code] = cached
                continue
            missing.append(code)
        
        if missing:
            total = len(missing)
            completed = 0
            if progress_callback:
                progress_callback(0, total, "开始获取行情数据...")
            
            # 提高并发数
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_code = {executor.submit(self._fetch_ma, code): code for code in missing}
                for future in as_completed(future_to_code):
                    code = future_to_code[future]
                    try:
                        ma = future.result(timeout=10) # 增加超时时间
                    except Exception:
                        ma = None
                    if ma:
                        cache[code] = {**ma, 'timestamp': time.time()}
                        result[code] = cache[code]
                    else:
                        cache[code] = {
                            'price': None, 'ma5': None, 'ma10': None, 'ma20': None,
                            'rsi': None, 'bb_upper': None, 'bb_middle': None, 'bb_lower': None,
                            'timestamp': time.time()
                        }
                    
                    completed += 1
                    if progress_callback:
                        # 每20条或者全部完成时输出
                        if completed % 20 == 0 or completed == total:
                            progress_callback(completed, total, f"获取行情数据: {completed}/{total}")
                        
            self._save_cache(self.ma_cache_file, cache)
        return result

    def get_selection(self, days=5, fund_type='social_security', force_update=False, date_str=None, progress_callback=None):
        date_str = date_str if date_str else datetime.datetime.now().strftime('%Y-%m-%d')
        ssf = SocialSecurityFund(fund_type=fund_type)
        
        # 获取或更新最后更新时间
        meta_cache_file = os.path.join(self.data_dir, 'national_team_meta.json')
        last_updated_at = None
        
        if force_update:
            last_updated_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                with open(meta_cache_file, 'w', encoding='utf-8') as f:
                    json.dump({'updated_at': last_updated_at}, f)
            except Exception:
                pass
        else:
            if os.path.exists(meta_cache_file):
                try:
                    with open(meta_cache_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        last_updated_at = meta.get('updated_at')
                except Exception:
                    pass
            if not last_updated_at:
                # 如果没有记录，默认为"未记录"
                last_updated_at = "未记录"
        
        if progress_callback:
            progress_callback(0, 0, "正在获取持仓列表...")
            
        holdings = ssf.get_latest_holdings(force_update=force_update)
        if holdings is None or holdings.empty:
            return pd.DataFrame(), {'date': date_str}
        holdings = holdings.copy()
        holdings['股票代码'] = holdings['股票代码'].astype(str).str.zfill(6)
        
        industry_map = self.get_stock_industry_map(holdings['股票代码'].tolist(), force_update=force_update, progress_callback=progress_callback)
        holdings['同花顺行业'] = holdings['股票代码'].map(industry_map).fillna('')
        
        if progress_callback:
            progress_callback(0, 0, "正在获取行情数据...")
            
        # 先获取所有持仓股票的行情数据（无论后续是否过滤），确保缓存完整
        all_codes = holdings['股票代码'].tolist()
        ma_map = self.get_stock_ma_map(all_codes, force_update=force_update, progress_callback=progress_callback)
            
        if progress_callback:
            progress_callback(0, 0, "正在获取主力雷达数据...")
            
        radar = FundRadar()
        df_sectors, used_info = radar.get_multi_day_data(date_str, days, cache_only=False)
        if df_sectors is None or df_sectors.empty:
            return pd.DataFrame(), {'date': date_str, 'used': used_info}
        df_sectors = df_sectors.copy()
        df_sectors['净流入'] = pd.to_numeric(df_sectors['净流入'], errors='coerce').fillna(0)
        inflow = df_sectors[df_sectors['净流入'] > 0]
        inflow_map = {self._normalize_industry(row['名称']): float(row['净流入']) for row in inflow.to_dict('records')}
        holdings['行业_norm'] = holdings['同花顺行业'].apply(self._normalize_industry)
        
        # 修改过滤逻辑：如果行业未知，也暂时保留，避免因接口故障导致所有数据被过滤
        # holdings = holdings[holdings['行业_norm'].isin(inflow_map.keys())]
        valid_industries = set(inflow_map.keys())
        def filter_industry(row):
            ind = row['行业_norm']
            if not ind: # 行业未知，保留
                return True
            return ind in valid_industries
            
        holdings = holdings[holdings.apply(filter_industry, axis=1)]
        
        if holdings.empty:
            return pd.DataFrame(), {'date': date_str, 'used': used_info, 'updated_at': last_updated_at}
            
        rows = []
        for row in holdings.to_dict('records'):
            code = row.get('股票代码')
            # 这里的 ma_map 已经包含了所有持仓股票的数据
            ma = ma_map.get(code, {})
            price = ma.get('price')
            ma5 = ma.get('ma5')
            ma10 = ma.get('ma10')
            ma20 = ma.get('ma20')
            rsi = ma.get('rsi')
            bb_upper = ma.get('bb_upper')
            bb_middle = ma.get('bb_middle')
            bb_lower = ma.get('bb_lower')
            
            above5 = price is not None and ma5 is not None and price >= ma5
            above10 = price is not None and ma10 is not None and price >= ma10
            above20 = price is not None and ma20 is not None and price >= ma20
            
            # 综合缠论建议
            hints = []
            chan_status = '震荡'
            
            # 1. 均线形态
            if above5 and above10 and above20:
                hints.append('多头')
                chan_status = '上涨'
            elif not above5 and not above10 and not above20:
                hints.append('空头')
                chan_status = '下跌'
            
            # 2. 布林线位置
            if price is not None and bb_upper is not None:
                if price > bb_upper:
                    hints.append('破上轨')
                elif price < bb_lower:
                    hints.append('破下轨')
                elif price > bb_middle:
                    hints.append('中轨上')
                else:
                    hints.append('中轨下')
            
            # 3. RSI状态
            if rsi is not None:
                if rsi > 75:
                    hints.append('超买')
                elif rsi < 25:
                    hints.append('超卖')
            
            # 4. 缠论近似判断
            final_advice = '中枢震荡'
            if chan_status == '上涨':
                if '超买' in hints or '破上轨' in hints:
                    final_advice = '顶背驰风险'
                elif price and ma5 and abs(price - ma5)/ma5 < 0.02: # 回踩MA5
                    final_advice = '三买观察'
                else:
                    final_advice = '强势延续'
            elif chan_status == '下跌':
                if '超卖' in hints or '破下轨' in hints:
                    final_advice = '一买潜伏'
                elif price and ma5 and abs(price - ma5)/ma5 < 0.02: # 反抽MA5
                    final_advice = '三卖风险'
                else:
                    final_advice = '弱势寻底'
            elif '中轨上' in hints and above5:
                 final_advice = '二买观察'
            
            hint = f"{final_advice} | {' '.join(hints)}"
            
            rows.append({
                '股票代码': code,
                '股票简称': row.get('股票简称'),
                '同花顺行业': row.get('同花顺行业'),
                '板块净流入(亿)': inflow_map.get(row.get('行业_norm'), 0),
                '持股市值(亿)': float(row.get('持股市值', 0)) / 1e8 if row.get('持股市值') is not None else 0,
                '最新价': price,
                'MA5': ma5,
                'MA10': ma10,
                'MA20': ma20,
                'RSI': rsi,
                '布林上轨': bb_upper,
                '布林中轨': bb_middle,
                '布林下轨': bb_lower,
                '站上MA5': '是' if above5 else '否',
                '站上MA10': '是' if above10 else '否',
                '站上MA20': '是' if above20 else '否',
                '缠论提示': hint,
            })
        df_out = pd.DataFrame(rows)
        # 默认按照持股市值降序排列
        if not df_out.empty:
            df_out = df_out.sort_values(by='持股市值(亿)', ascending=False)
            
        return df_out, {'date': date_str, 'used': used_info, 'updated_at': last_updated_at}
