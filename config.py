import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """
    整体配置说明：
    - 现在只做单机/单用户使用，不接鉴权，但数据库模型里预留了 owner 字段的位置，
      以后要加用户系统时，直接在这里挂一个 auth 蓝图即可，不需要推翻现在的结构。
    - 数据库先用 SQLite，路径放在项目根目录下的 instance/futures_lab.db。
      以后数据量大了/要多人共用，把 SQLALCHEMY_DATABASE_URI 换成 PostgreSQL 连接串即可，
      上层代码（models / analysis engine / 路由）都不需要改。
    """
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'futures_lab.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
