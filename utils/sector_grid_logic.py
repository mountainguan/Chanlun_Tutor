import os
import json
import pandas as pd
from datetime import datetime

# Sector Mapping based on Akshare THS Summary (Native Structure)
# Grouped by TDX/Shenwan Level 1 Industries (Approximate Mapping)
SECTOR_MAPPING = {
    "石油": ["油气开采及服务", "石油加工贸易"],
    "煤炭": ["煤炭开采加工"],
    "化工": ["农化制品", "化学原料", "化学制品", "电子化学品", "塑料制品", "橡胶制品", "化学纤维"],
    "钢铁": ["钢铁"],
    "有色": ["贵金属", "能源金属", "工业金属", "金属新材料", "小金属"],
    "建材": ["非金属材料", "建筑材料"],
    "建筑": ["建筑装饰"],
    "房地产": ["房地产"],
    "机械设备": ["轨交设备", "专用设备", "工程机械", "通用设备", "自动化设备"],
    "电力设备": ["电网设备", "风电设备", "电池", "光伏设备", "电机", "其他电源设备"],
    "国防军工": ["军工装备", "军工电子"],
    "汽车": ["汽车服务及其他", "汽车零部件", "汽车整车"],
    "商贸": ["贸易", "零售", "互联网电商"],
    "家电": ["小家电", "厨卫电器", "白色家电", "黑色家电"],
    "纺织服饰": ["纺织制造", "服装家纺"],
    "轻工制造": ["家居用品", "造纸", "包装印刷"],
    "食品饮料": ["饮料制造", "食品加工制造", "白酒"],
    "农林牧渔": ["种植业与林业", "农产品加工", "养殖业"],
    "医药医疗": ["医药商业", "中药", "医疗器械", "化学制药", "生物制品", "医疗服务"],
    "美容护理": ["美容护理"],
    "公共事业": ["燃气", "电力"],
    "交通运输": ["物流", "公路铁路运输", "港口航运", "机场航运"],
    "环保": ["环境治理", "环保设备"],
    "银行": ["银行"],
    "非银金融": ["多元金融", "证券", "保险"],
    "电子": ["消费电子", "其他电子", "半导体", "元件", "光学光电子"],
    "通信": ["通信设备", "通信服务"],
    "计算机": ["计算机设备", "IT服务", "软件开发"],
    "传媒": ["游戏", "影视院线", "文化传媒"],
    "社会服务": ["教育", "旅游及酒店", "其他社会服务"],
    "综合": ["综合"]
}

# Synonyms/Fuzzy Matching - Not needed as we use native THS names now
NAME_ALIASES = {}

def normalize_sector_name(name):
    """Normalize sector name to match the mapping keys."""
    if name in NAME_ALIASES:
        return NAME_ALIASES[name]
    # Try to find if the name is already in the mapping values
    for group, sectors in SECTOR_MAPPING.items():
        if name in sectors:
            return name
    return name

def get_sector_grid_data(cache_dir, days=6):
    """
    Reads the last N days of sector_sina_*.json files and aggregates data.
    Returns a dictionary structured for the UI grid.
    """
    files = [f for f in os.listdir(cache_dir) if f.startswith("sector_sina_") and f.endswith(".json")]
    files.sort() # Date order
    
    # Take last N files
    target_files = files[-days:] if len(files) >= days else files
    
    # Structure: { Date: { SectorName: { change: float, net_inflow: float, turnover: float } } }
    history_data = {}
    dates = []
    
    for filename in target_files:
        date_str = filename.replace("sector_sina_", "").replace(".json", "")
        # Format date as MM.DD for display
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = f"{dt.month}.{dt.day:02d}"
        except:
            display_date = date_str
            
        dates.append(display_date)
        
        filepath = os.path.join(cache_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                sectors = data.get("sina_sectors", [])
                
                day_data = {}
                for s in sectors:
                    name = s.get("名称")
                    # Normalize name
                    norm_name = normalize_sector_name(name)
                    
                    day_data[norm_name] = {
                        "change": s.get("涨跌幅", 0),
                        "net_inflow": s.get("净流入", 0),
                        "turnover": s.get("总成交额", 0)
                    }
                history_data[display_date] = day_data
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            
    # Build the final grid structure
    # { Category: [ { Name: SectorName, History: [ { date: ..., status: ... } ] } ] }
    
    grid_data = {}
    
    for category, sector_list in SECTOR_MAPPING.items():
        # Add entry for this category
        grid_data[category] = []
        
        for sector_name in sector_list:
            sector_history = []
            recent_inflow_sum = 0
            
            for date in dates:
                day_stats = history_data.get(date, {}).get(sector_name)
                
                status = "-"
                color_class = "bg-gray-50 text-gray-300"
                inflow = 0
                turnover = 0
                ratio = 0
                
                if day_stats:
                    inflow = day_stats.get("net_inflow", 0)
                    turnover = day_stats.get("turnover", 0)
                    
                    recent_inflow_sum += inflow
                    
                    if turnover > 0:
                        ratio = (inflow / turnover) * 100
                    else:
                        ratio = 0
                        
                    # Logic based on Ratio (Flow Intensity)
                    if ratio > 8:
                        status = "超入"
                        color_class = "bg-red-600 text-white"
                    elif ratio > 3:
                        status = "强入"
                        color_class = "bg-red-400 text-white"
                    elif ratio > 0:
                        status = "弱入"
                        color_class = "bg-red-100 text-red-800"
                    elif ratio < -8:
                        status = "超出"
                        color_class = "bg-green-600 text-white"
                    elif ratio < -3:
                        status = "强出"
                        color_class = "bg-green-400 text-white"
                    else: # ratio < 0
                        status = "弱出"
                        color_class = "bg-green-100 text-green-800"
                
                sector_history.append({
                    "date": date,
                    "status": status,
                    "color_class": color_class,
                    "inflow": inflow,
                    "turnover": turnover,
                    "ratio": ratio
                })
            
            grid_data[category].append({
                "name": sector_name,
                "history": sector_history,
                "total_inflow": recent_inflow_sum
            })
            
        # Optional: Sort sectors within category by total inflow (Descending)
        # grid_data[category].sort(key=lambda x: x['total_inflow'], reverse=True)

    return dates, grid_data
