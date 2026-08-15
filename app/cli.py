# -*- coding: utf-8 -*-
"""
把 app/data_import.py 里的导入函数包成 `flask import-xxx` 命令行命令，
这样接真实数据时不用写任何 Python 代码，落地一份格式正确的 CSV 然后跑一条命令就行。

用法示例（在项目根目录下）：
    flask --app run.py import-daily-bar path/to/daily_bar.csv
    flask --app run.py import-position-rank path/to/position_rank.csv
    flask --app run.py import-warehouse-receipt path/to/warehouse_receipt.csv
    flask --app run.py import-basis path/to/basis.csv
    flask --app run.py import-macro-data path/to/macro_data.csv

每条命令跑完会打印插入/更新的行数，以及被跳过的行（行号+原因），
跳过不代表整个导入失败——其余行照常入库。
"""
import click


def _report(label, result):
    click.echo(f"{label} 导入完成：新增 {result['inserted']} 行，更新 {result['updated']} 行。")
    if result["skipped"]:
        click.echo(f"以下 {len(result['skipped'])} 行被跳过，未导入：")
        for line_no, reason in result["skipped"]:
            click.echo(f"  第 {line_no} 行: {reason}")


def register_cli(app):
    from app.data_import import (
        import_daily_bar_csv,
        import_position_rank_csv,
        import_warehouse_receipt_csv,
        import_basis_csv,
        import_macro_data_csv,
    )

    @app.cli.command("import-daily-bar")
    @click.argument("path")
    def import_daily_bar_command(path):
        """导入日线行情 CSV（开高低收结算/成交量/持仓量）。"""
        _report("日线行情", import_daily_bar_csv(path))

    @app.cli.command("import-position-rank")
    @click.argument("path")
    def import_position_rank_command(path):
        """导入持仓龙虎榜 CSV（总持仓/前5多空占比）。"""
        _report("持仓龙虎榜", import_position_rank_csv(path))

    @app.cli.command("import-warehouse-receipt")
    @click.argument("path")
    def import_warehouse_receipt_command(path):
        """导入仓单日报 CSV。"""
        _report("仓单日报", import_warehouse_receipt_csv(path))

    @app.cli.command("import-basis")
    @click.argument("path")
    def import_basis_command(path):
        """导入期现基差 CSV。"""
        _report("期现基差", import_basis_csv(path))

    @app.cli.command("import-macro-data")
    @click.argument("path")
    def import_macro_data_command(path):
        """导入宏观数据 CSV。"""
        _report("宏观数据", import_macro_data_csv(path))
