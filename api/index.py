import sys
import os

# 将项目根目录添加到 python path，以便可以正确导入 main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicegui import app
# 导入 main 模块以加载 UI 定义
import main


# 这对于在 Vercel 上运行是必要的
if __name__ == '__main__':
    from nicegui import ui
    ui.run()
