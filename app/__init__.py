import os

from flask import Flask

from config import Config
from app.extensions import db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    instance_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance")
    os.makedirs(instance_dir, exist_ok=True)

    db.init_app(app)

    # 蓝图按模块拆分，现在没有用户系统，以后要加鉴权/多用户时，
    # 直接新增一个 auth 蓝图并在这里注册即可，不需要改动其它蓝图。
    from app.blueprints.main.routes import main_bp
    from app.blueprints.case.routes import case_bp
    from app.blueprints.calendar.routes import calendar_bp
    from app.blueprints.position.routes import position_bp
    from app.blueprints.principles.routes import principles_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(case_bp, url_prefix="/case")
    app.register_blueprint(calendar_bp, url_prefix="/calendar")
    app.register_blueprint(position_bp, url_prefix="/position")
    app.register_blueprint(principles_bp, url_prefix="/principles")

    with app.app_context():
        db.create_all()

    # flask import-xxx 系列命令，用于真实数据的批量录入（时间序列表）
    from app.cli import register_cli
    register_cli(app)

    # /admin 后台，用于人工维护的表（案例、事前状态、生产端、产业链、政策等）
    from app.admin import register_admin
    register_admin(app)

    return app
