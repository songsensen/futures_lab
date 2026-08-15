from flask import Blueprint, render_template, abort

from app.models import Variety, Event
from app.analysis import (
    get_price_snapshot,
    get_position_snapshot,
    get_basis_snapshot,
    compute_factor_status,
    match_historical_cases,
    compute_setup_signal,
    match_setup_precedents,
    compute_margin_signal,
    compute_chip_anomaly_signal,
    get_case_comparison_series,
    get_case_precedent_stats,
    get_setup_episode_regions,
    compute_composite_signal,
    get_case_risk_reward,
    summarize_case_risk_reward,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def variety_list():
    varieties = Variety.query.order_by(Variety.sector, Variety.code).all()
    cards = []
    for v in varieties:
        price_snap = get_price_snapshot(v)
        cards.append({"variety": v, "price_snap": price_snap})
    return render_template("main/variety_list.html", cards=cards)


@main_bp.route("/variety/<code>")
def variety_detail(code):
    variety = Variety.query.filter_by(code=code).first()
    if not variety:
        abort(404)

    price_snap = get_price_snapshot(variety)
    position_snap = get_position_snapshot(variety)
    basis_snap = get_basis_snapshot(variety)
    factor_status = compute_factor_status(variety, price_snap, position_snap)

    # 三条事前状态通道要先算出来，才能让案例匹配知道"现在到底是哪条通道在响"，
    # 而不是像之前那样匹配逻辑只认价格分位、完全没用上利润/筹码这两条独立通道。
    setup_signal = compute_setup_signal(variety)
    setup_precedents = match_setup_precedents(variety, setup_signal, dimension="价格")
    margin_signal = compute_margin_signal(variety)
    margin_precedents = match_setup_precedents(variety, margin_signal, dimension="利润")
    chip_signal = compute_chip_anomaly_signal(variety)

    matched_cases, filtered_case_count = match_historical_cases(
        variety, factor_status, price_snap,
        setup_signal=setup_signal, margin_signal=margin_signal, chip_signal=chip_signal,
    )
    for m in matched_cases:
        m["comparison"] = get_case_comparison_series(variety, m["case"])
        m["precedent_stats"] = get_case_precedent_stats(m["case"])
        m["risk_reward"] = get_case_risk_reward(m["comparison"])

    # 决策参考：把上面四路独立信号(价格分位/利润状态/筹码仓单/历史案例)的方向摆在一起
    # 对齐成一个措辞克制的结论，以及把匹配案例的历史价格路径提炼成风险回报参考区间——
    # 这两块是"从证据罗列到决策参考"这一步专门补的，此前这两步都要用户自己在脑子里做。
    composite_signal = compute_composite_signal(setup_signal, margin_signal, chip_signal, matched_cases)
    risk_reward_summary = summarize_case_risk_reward(matched_cases)

    setup_regions = get_setup_episode_regions(variety, dimension="价格")

    kline_data = []
    events_for_chart = []
    if price_snap:
        for b in price_snap["bars"]:
            kline_data.append([
                b.trade_date.isoformat(), b.open, b.close, b.low, b.high, b.volume or 0,
                b.open_interest or 0,
            ])
        events = Event.query.filter_by(variety_id=variety.id).order_by(Event.event_date).all()
        for e in events:
            events_for_chart.append({
                "date": e.event_date.isoformat(),
                "title": e.title,
                "level": e.level,
                "factor": e.factor_tag.name if e.factor_tag else "",
                "source": e.source or "",
                # 之前用 source 字符串反推"这是不是案例锚点"，现在有了真正的外键就直接用它，
                # 不再靠字符串猜测。
                "is_case": e.case_id is not None,
                "is_failure": bool(e.case and e.case.is_failure_case),
            })

    return render_template(
        "main/variety_detail.html",
        variety=variety,
        price_snap=price_snap,
        position_snap=position_snap,
        basis_snap=basis_snap,
        factor_status=factor_status,
        matched_cases=matched_cases,
        filtered_case_count=filtered_case_count,
        composite_signal=composite_signal,
        risk_reward_summary=risk_reward_summary,
        setup_signal=setup_signal,
        setup_precedents=setup_precedents,
        margin_signal=margin_signal,
        margin_precedents=margin_precedents,
        chip_signal=chip_signal,
        setup_regions=setup_regions,
        kline_data=kline_data,
        events_for_chart=events_for_chart,
    )
