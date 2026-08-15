"""
本地启动入口：python run.py
首次启动会自动建库 + 灌入测试数据（品种/K线/持仓/仓单/案例/事件/宏观政策全部是模拟数据），
之后每次启动检测到数据已存在就不会重复灌入。
"""
from app import create_app
from app.seed import run_seed

app = create_app()

with app.app_context():
    run_seed()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
