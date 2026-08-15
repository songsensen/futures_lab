# -*- coding: utf-8 -*-
"""
真实数据录入接口 —— 时间序列表专用
====================================
这里只覆盖"高频追加、有唯一约束、天然适合批量导入"的五张表：
    daily_bar / position_rank / warehouse_receipt / basis / macro_data
（案例、事前状态、生产端、产业链这些需要人工判断/写文字说明的表，走 /admin 后台单条录入，
 不放在这里 —— 参见 app/admin.py 顶部的说明。）

设计原则：
1. 只认 CSV，列名和顺序固定（见每个函数的 docstring），不做智能列名匹配 —— 简单直接，
   出错也容易定位是哪一列错了。
2. 全部走 upsert：按每张表已有的唯一约束（contract_id+trade_date 或 indicator+report_date）
   判断是插入还是更新，重复导入同一份文件是安全的，不会产生重复行。
3. daily_bar / position_rank / warehouse_receipt / basis 四张表都是挂在 contract 下面的，
   CSV 里直接写 variety_code + contract_code，函数自动按 variety_code 找到品种、
   按 contract_code 找到或创建 contract 记录 —— 不需要先去后台手动建好 contract 再导数据。
4. 每个函数返回 {"inserted": n, "updated": n, "skipped": [(行号, 原因), ...]}，
   跳过的行不会中断整个导入，方便一次性看到这批数据里所有有问题的行，而不是导一半报错退出。

用法（命令行，见 app/cli.py 注册的 flask 命令）：
    flask import-daily-bar path/to/daily_bar.csv
    flask import-position-rank path/to/position_rank.csv
    flask import-warehouse-receipt path/to/warehouse_receipt.csv
    flask import-basis path/to/basis.csv
    flask import-macro-data path/to/macro_data.csv

也可以在代码/shell 里直接调用同名的 import_xxx_csv(path) 函数。
"""
import csv
from datetime import datetime

from app.extensions import db
from app.models import Variety, Contract, DailyBar, PositionRank, WarehouseReceipt, Basis, MacroData


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_float(s):
    s = (s or "").strip()
    return float(s) if s else None


def _parse_int(s):
    s = (s or "").strip()
    return int(float(s)) if s else None


def _parse_bool(s):
    s = (s or "").strip().lower()
    return s in ("1", "true", "yes", "y", "是")


def _get_or_create_contract(variety_code, contract_code):
    """
    按 variety_code 找品种、按 contract_code 找/建 contract。
    品种必须已存在（品种是低频维护表，走 /admin 手动建，不在导入脚本里顺手创建，
    避免拼错品种代码时系统"自动"生成一个没人注意到的垃圾品种）。
    contract 可以顺手创建 —— 一个品种加一个新合约是常见操作，没必要先去后台点一下。
    """
    variety = Variety.query.filter_by(code=variety_code).first()
    if not variety:
        raise ValueError(f"品种代码不存在: {variety_code}（请先在 /admin 后台创建该品种）")

    contract = Contract.query.filter_by(contract_code=contract_code).first()
    if not contract:
        contract = Contract(variety_id=variety.id, contract_code=contract_code, is_main=True)
        db.session.add(contract)
        db.session.flush()  # 拿到 contract.id，供本行后面使用
    return contract


def _run_import(path, row_handler):
    """
    公共的"读CSV -> 逐行调用 row_handler -> 统计结果"骨架，五个 import_xxx_csv 函数
    都是这个骨架的薄封装，只是 row_handler 不同。row_handler 返回 "inserted" / "updated"，
    抛异常则该行记为 skipped，不影响其余行。
    """
    inserted = updated = 0
    skipped = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):  # 第1行是表头，数据从第2行开始
            try:
                result = row_handler(row)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
            except Exception as exc:  # noqa: BLE001 —— 导入脚本里就是要把任何单行错误都兜住
                db.session.rollback()
                skipped.append((line_no, str(exc)))
    if inserted or updated:
        db.session.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_daily_bar_csv(path):
    """
    列: variety_code,contract_code,trade_date,open,high,low,close,settle,volume,open_interest
    唯一键: (contract_id, trade_date) —— 已存在则更新那一行的行情数据，不存在则插入。
    """
    def handle(row):
        contract = _get_or_create_contract(row["variety_code"].strip(), row["contract_code"].strip())
        trade_date = _parse_date(row["trade_date"])
        bar = DailyBar.query.filter_by(contract_id=contract.id, trade_date=trade_date).first()
        is_new = bar is None
        if is_new:
            bar = DailyBar(contract_id=contract.id, trade_date=trade_date)
            db.session.add(bar)
        bar.open = _parse_float(row.get("open"))
        bar.high = _parse_float(row.get("high"))
        bar.low = _parse_float(row.get("low"))
        bar.close = _parse_float(row.get("close"))
        bar.settle = _parse_float(row.get("settle"))
        bar.volume = _parse_int(row.get("volume"))
        bar.open_interest = _parse_int(row.get("open_interest"))
        return "inserted" if is_new else "updated"

    return _run_import(path, handle)


def import_position_rank_csv(path):
    """
    列: variety_code,contract_code,trade_date,total_open_interest,top5_long_ratio,top5_short_ratio
    唯一键: (contract_id, trade_date)
    """
    def handle(row):
        contract = _get_or_create_contract(row["variety_code"].strip(), row["contract_code"].strip())
        trade_date = _parse_date(row["trade_date"])
        pr = PositionRank.query.filter_by(contract_id=contract.id, trade_date=trade_date).first()
        is_new = pr is None
        if is_new:
            pr = PositionRank(contract_id=contract.id, trade_date=trade_date)
            db.session.add(pr)
        pr.total_open_interest = _parse_int(row.get("total_open_interest"))
        pr.top5_long_ratio = _parse_float(row.get("top5_long_ratio"))
        pr.top5_short_ratio = _parse_float(row.get("top5_short_ratio"))
        return "inserted" if is_new else "updated"

    return _run_import(path, handle)


def import_warehouse_receipt_csv(path):
    """
    列: variety_code,contract_code,trade_date,receipt_qty
    唯一键: (contract_id, trade_date)
    """
    def handle(row):
        contract = _get_or_create_contract(row["variety_code"].strip(), row["contract_code"].strip())
        trade_date = _parse_date(row["trade_date"])
        wr = WarehouseReceipt.query.filter_by(contract_id=contract.id, trade_date=trade_date).first()
        is_new = wr is None
        if is_new:
            wr = WarehouseReceipt(contract_id=contract.id, trade_date=trade_date)
            db.session.add(wr)
        wr.receipt_qty = _parse_int(row.get("receipt_qty"))
        return "inserted" if is_new else "updated"

    return _run_import(path, handle)


def import_basis_csv(path):
    """
    列: variety_code,contract_code,trade_date,futures_price,spot_price,basis_value
    唯一键: (contract_id, trade_date)。basis_value 留空时自动按 spot_price - futures_price 计算。
    """
    def handle(row):
        contract = _get_or_create_contract(row["variety_code"].strip(), row["contract_code"].strip())
        trade_date = _parse_date(row["trade_date"])
        b = Basis.query.filter_by(contract_id=contract.id, trade_date=trade_date).first()
        is_new = b is None
        if is_new:
            b = Basis(contract_id=contract.id, trade_date=trade_date)
            db.session.add(b)
        b.futures_price = _parse_float(row.get("futures_price"))
        b.spot_price = _parse_float(row.get("spot_price"))
        basis_value = _parse_float(row.get("basis_value"))
        if basis_value is None and b.futures_price is not None and b.spot_price is not None:
            basis_value = b.spot_price - b.futures_price
        b.basis_value = basis_value
        return "inserted" if is_new else "updated"

    return _run_import(path, handle)


def import_macro_data_csv(path):
    """
    列: indicator,report_date,value
    唯一键: (indicator, report_date)。不挂品种，宏观数据全市场共用。
    """
    def handle(row):
        indicator = row["indicator"].strip()
        report_date = _parse_date(row["report_date"])
        md = MacroData.query.filter_by(indicator=indicator, report_date=report_date).first()
        is_new = md is None
        if is_new:
            md = MacroData(indicator=indicator, report_date=report_date)
            db.session.add(md)
        md.value = _parse_float(row.get("value"))
        return "inserted" if is_new else "updated"

    return _run_import(path, handle)


IMPORTERS = {
    "daily_bar": import_daily_bar_csv,
    "position_rank": import_position_rank_csv,
    "warehouse_receipt": import_warehouse_receipt_csv,
    "basis": import_basis_csv,
    "macro_data": import_macro_data_csv,
}
