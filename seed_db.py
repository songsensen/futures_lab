"""
手动重建数据库并重新灌入测试数据：python seed_db.py --reset
不带 --reset 参数时，行为和 run.py 启动时一样，只在数据库为空时才灌入。
"""
import sys

from app import create_app
from app.extensions import db
from app.seed import run_seed

app = create_app()

with app.app_context():
    if "--reset" in sys.argv:
        db.drop_all()
        db.create_all()
        print("已清空并重建表结构。")
    run_seed()
    print("测试数据已就位（如果之前已有数据，本次没有重复灌入）。")

