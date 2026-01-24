import sys
import os

# 配置环境变量以允许在只读文件系统中写入临时文件
os.environ['XDG_CONFIG_HOME'] = '/tmp'
os.environ['MPLCONFIGDIR'] = '/tmp'  # Just in case matplotlib is used indirectly

# 改变当前工作目录到 /tmp，这样 NiceGUI (或者其他库) 尝试在当前目录创建 .nicegui 文件夹时不会报错
# 注意：这必须在导入 main 之前完成
try:
    os.chdir('/tmp')
except FileNotFoundError:
    pass # 本地开发可能没有 /tmp

# 将项目根目录添加到 python path，以便可以正确导入 main.py
# 假设 api/index.py 在 api/ 文件夹下，项目根目录是上一级
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from nicegui import app
# 导入 main 模块以加载 UI 定义
import main


# 这对于在 Vercel 上运行是必要的
if __name__ == '__main__':
    from nicegui import ui
    ui.run()
