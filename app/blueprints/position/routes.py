# -*- coding: utf-8 -*-
"""
持仓/仓单分析蓝图：品种详情页(main蓝图)里已经有一份"持仓/仓单现状快照"的摘要卡片，
这个蓝图是它的展开版——把 get_position_snapshot 返回的持仓量、仓单量、虚实盘比
完整时间序列画成走势图，而不是只看最新一天的数字。

这里没有独立的"持仓分析"计算逻辑，用的还是 app/analysis.py 里 get_position_snapshot /
get_price_snapshot 这两个已有函数，这个蓝图只负责把它们的结果整理成图表需要的数组格式。
"""
from flask import Blueprint, render_template, abort

from app.models import Variety
from app.analysis import get_position_snapshot, get_price_snapshot

position_bp = Blueprint("position", __name__)


@position_bp.route("/")
def position_index():
    """品种入口列表，点进去才是真正的持仓/仓单走势图（见 position_detail）。"""
    varieties = Variety.query.order_by(Variety.code).all()
    return render_template("position/position_index.html", varieties=varieties)


@position_bp.route("/<code>")
def position_detail(code):
    variety = Variety.query.filter_by(code=code).first()
    if not variety:
        abort(404)
    position_snap = get_position_snapshot(variety)
    price_snap = get_price_snapshot(variety)

    # position_snap["pos_rows"] 和 ["wh_rows"] 是两张独立的表(PositionRank/WarehouseReceipt)
    # 各自的完整历史，交易日不一定完全对齐(比如某天只录了持仓龙虎榜没录仓单)，所以按日期建一个
    # wh_map 做查找式对齐，而不是假设两个列表能直接按下标一一对应，那样一旦某天缺记录，
    # 后面所有下标都会错位。
    chart_dates, oi_series, wh_series, ratio_series = [], [], [], []
    if position_snap:
        wh_map = {w.trade_date: w.receipt_qty for w in position_snap["wh_rows"]}
        for p in position_snap["pos_rows"]:
            chart_dates.append(p.trade_date.isoformat())
            oi_series.append(p.total_open_interest)
            wh = wh_map.get(p.trade_date)
            wh_series.append(wh)
            # 仓单量当天没有记录，或者是0，都不能拿来当分母，直接留 None(前端画图时是断点，
            # 不会画出一个虚假的比值)。
            ratio_series.append(round(p.total_open_interest / wh, 1) if wh else None)

    return render_template(
        "position/position_detail.html",
        variety=variety, position_snap=position_snap, price_snap=price_snap,
        chart_dates=chart_dates, oi_series=oi_series, wh_series=wh_series, ratio_series=ratio_series,
    )
