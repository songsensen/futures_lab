# -*- coding: utf-8 -*-
"""
分析引擎
========
这里落地的是前面讨论里反复提到的那条推理链：

    现状快照（价格/持仓分位、虚实盘比、基差）
        -> 对照品种的关键因素清单，标出"现在哪个因素处于激活状态"
        -> 拿"激活的因素 + 当前基本面状态"去检索历史案例库
        -> 返回带匹配理由的相似案例列表（不给"预测"，只给"参照系"）

几个刻意做的设计决策，对应前面讨论过的坑：
- 相似度匹配不是只看价格百分位，而是"因素标签命中 + 基本面状态（库存/需求/盈亏）"
  组合打分，价格位置只是加分项，不是唯一依据——避免"表面像、本质不同"的误匹配。
- 如果一个品种没有任何案例，或者打分后没有案例过线，诚实返回空列表，页面要显示
  "没有直接参照"，不能为了好看硬凑一个不相关的案例。
- factor 的 current_status 计算只是一个规则性的启发式（最近N天内有没有同标签的
  Event），不是什么智能算法，说清楚这一点很重要：这是辅助梳理，不是自动信号。
"""
from datetime import timedelta

from app.models import (
    Case,
    DailyBar,
    Event,
    PositionRank,
    WarehouseReceipt,
    Basis,
    Variety,
    VarietyFactor,
    Contract,
    SetupEpisode,
    ProfitMarginRecord,
    MacroData,
)

RECENT_EVENT_WINDOW_DAYS = 60  # "最近发生过同标签事件"的观察窗口
MIN_MATCH_SCORE = 2  # 情景匹配打分低于此值就不展示，宁可空着也不硬凑


def _main_contract(variety: Variety):
    return Contract.query.filter_by(variety_id=variety.id, is_main=True).first()


def get_price_snapshot(variety: Variety):
    """价格现状体检：最新价、历史百分位、距最高/最低点位置"""
    contract = _main_contract(variety)
    if not contract:
        return None

    bars = (
        DailyBar.query.filter_by(contract_id=contract.id)
        .order_by(DailyBar.trade_date)
        .all()
    )
    if not bars:
        return None

    closes = [b.close for b in bars if b.close is not None]
    latest = bars[-1]
    percentile = _percentile_rank(closes, latest.close)

    return {
        "latest_date": latest.trade_date,
        "latest_close": latest.close,
        "percentile": percentile,
        "hist_low": min(closes),
        "hist_high": max(closes),
        "bars": bars,
    }


def get_position_snapshot(variety: Variety):
    """持仓/仓单现状体检：持仓历史百分位、虚实盘比、多空集中度"""
    contract = _main_contract(variety)
    if not contract:
        return None

    pos_rows = (
        PositionRank.query.filter_by(contract_id=contract.id)
        .order_by(PositionRank.trade_date)
        .all()
    )
    wh_rows = (
        WarehouseReceipt.query.filter_by(contract_id=contract.id)
        .order_by(WarehouseReceipt.trade_date)
        .all()
    )
    if not pos_rows:
        return None

    oi_series = [p.total_open_interest for p in pos_rows if p.total_open_interest]
    latest_pos = pos_rows[-1]
    oi_percentile = _percentile_rank(oi_series, latest_pos.total_open_interest)

    latest_wh = wh_rows[-1] if wh_rows else None
    virtual_real_ratio = None
    if latest_wh and latest_wh.receipt_qty:
        virtual_real_ratio = round(latest_pos.total_open_interest / latest_wh.receipt_qty, 1)

    alert = virtual_real_ratio is not None and virtual_real_ratio > 100  # 讨论里提到的100:1警惕阈值

    return {
        "latest_date": latest_pos.trade_date,
        "total_open_interest": latest_pos.total_open_interest,
        "oi_percentile": oi_percentile,
        "top5_long_ratio": latest_pos.top5_long_ratio,
        "top5_short_ratio": latest_pos.top5_short_ratio,
        "latest_receipt": latest_wh.receipt_qty if latest_wh else None,
        "virtual_real_ratio": virtual_real_ratio,
        "virtual_real_alert": alert,
        "pos_rows": pos_rows,
        "wh_rows": wh_rows,
    }


def get_basis_snapshot(variety: Variety):
    contract = _main_contract(variety)
    if not contract:
        return None
    rows = Basis.query.filter_by(contract_id=contract.id).order_by(Basis.trade_date).all()
    if not rows:
        return None
    latest = rows[-1]
    return {
        "latest_date": latest.trade_date,
        "basis_value": latest.basis_value,
        "state": "升水" if latest.basis_value and latest.basis_value < 0 else "贴水",
        "rows": rows,
    }


def compute_factor_status(variety: Variety, price_snap, position_snap):
    """
    给每条关注点算一个"现在是不是活跃"的状态：
    - 有最近事件命中同标签 -> 按事件等级给"异常"或"偏热"
    - 没有事件命中，但价格/持仓分位处于极端区间，也顺带给一个启发式的"偏热"提示
    - 否则就是"平静"
    这不是智能判断，只是一个规则过滤器，帮你把关注清单从"一段固定文字"变成"体检报告"。
    """
    results = []
    if not price_snap and not position_snap:
        return results

    horizon = price_snap["latest_date"] if price_snap else position_snap["latest_date"]
    window_start = horizon - timedelta(days=RECENT_EVENT_WINDOW_DAYS)

    for vf in VarietyFactor.query.filter_by(variety_id=variety.id).order_by(VarietyFactor.importance_rank.desc()):
        recent_events = (
            Event.query.filter(
                Event.variety_id == variety.id,
                Event.factor_tag_id == vf.factor_tag_id,
                Event.event_date >= window_start,
                Event.event_date <= horizon,
            )
            .order_by(Event.event_date.desc())
            .all()
        )

        if recent_events:
            top_level = max(e.level for e in recent_events)
            status = "异常" if top_level >= 3 else "偏热"
            reason = f"近{RECENT_EVENT_WINDOW_DAYS}天内命中{len(recent_events)}条相关事件，最近一条：{recent_events[0].title}"
        elif price_snap and price_snap["percentile"] is not None and (
            price_snap["percentile"] >= 90 or price_snap["percentile"] <= 10
        ):
            status = "偏热"
            reason = f"价格处于历史{price_snap['percentile']}%分位的极端区间，即便没有新事件也值得多看一眼"
        else:
            status = "平静"
            reason = "近期没有命中相关事件，也不处于极端分位"

        results.append(
            {
                "factor": vf,
                "status": status,
                "reason": reason,
                "recent_events": recent_events,
            }
        )
    return results


def _bucket_from_percentile(pct):
    if pct is None:
        return None
    if pct >= 66:
        return "高位"
    if pct <= 33:
        return "低位"
    return "中位"


def _score_label(score):
    """把内部打分换算成一个不需要解释就能看懂的标签，而不是让人猜"4分算高还是低"。"""
    if score >= 5:
        return "强匹配"
    if score >= 3:
        return "中等匹配"
    return "弱匹配"


def match_historical_cases(
    variety: Variety, factor_status, price_snap,
    setup_signal=None, margin_signal=None, chip_signal=None, top_n=3,
):
    """
    历史情景匹配：不是只比价格位置，而是"当前激活的因素标签 + 基本面状态桶 + 当前正在
    触发的事前状态通道"组合打分。
    打分规则（刻意保持简单、可解释，方便你直接看懂"为什么匹配到这条"）：
      +2  案例的驱动因素标签，正好是当前处于"偏热/异常"状态的因素
      +1  案例的库存状态桶 与 当前价格分位推出的库存/位置桶 一致（用价格分位做粗略代理）
      +1  案例本身就发生在同一个品种上（跨品种案例可以匹配上但分数天然更低，
          仍然可能因为因素标签命中而被召回，呼应"跨品种联动"的讨论）
      +2  案例对应的"事前状态"(SetupEpisode) 的维度/机制，正好是当前实际触发的那条通道——
          比如现在是"筹码异常"在响，而这条案例当时也是"资金布局型"催生的，这一层之前完全
          没接进匹配逻辑，等于做了三条独立信号通道，但案例检索还只认价格分位，这里补上。
    低于 MIN_MATCH_SCORE 的直接过滤掉，宁可返回空列表也不硬凑；同时把"因为分数不够被筛掉
    多少条"如实报出来，而不是让用户以为算法只找到这么几条相关的。
    """
    hot_factor_ids = {fs["factor"].factor_tag_id for fs in factor_status if fs["status"] in ("偏热", "异常")}
    current_bucket = _bucket_from_percentile(price_snap["percentile"]) if price_snap else None

    candidates = Case.query.filter(
        db_or_same_variety_or_shared_tag(variety, hot_factor_ids)
    ).all()

    price_extreme = bool(setup_signal and setup_signal.get("in_extreme_zone"))
    margin_extreme = bool(margin_signal and margin_signal.get("in_extreme_zone"))
    chip_triggered = bool(chip_signal and chip_signal.get("triggered"))

    scored = []
    below_threshold = 0
    for case in candidates:
        score = 0
        reasons = []

        if case.event_type_id in hot_factor_ids:
            score += 2
            reasons.append(f"驱动因素「{case.event_type.name if case.event_type else '未知'}」当前正处于激活状态")

        if current_bucket and case.inventory_level_then:
            # 用"价格位置"粗略代理"基本面松紧"：价格低位常对应高库存/供应过剩，反之亦然，
            # 这是一个明显的简化，实际使用中应该换成真实的库存数据字段。
            proxy_bucket = {"高位": "低位", "中位": "中位", "低位": "高位"}.get(current_bucket)
            if case.inventory_level_then == proxy_bucket:
                score += 1
                reasons.append(f"当前价格位置与该案例当时的库存状态（{case.inventory_level_then}）吻合")

        if case.variety_id == variety.id:
            score += 1
            reasons.append("同品种历史案例")

        # 这条案例当时是由哪个 SetupEpisode 演变来的？拿它的 dimension/mechanism 去对
        # 当前三条独立通道里"正在响"的那条，对上了才加分——而不是只看价格位置。
        episode = SetupEpisode.query.filter_by(led_to_case_id=case.id).first()
        if episode:
            if episode.dimension == "价格" and price_extreme:
                score += 2
                reasons.append("该案例当时由价格维度的极端状态催生，与当前价格极端状态属于同一类型")
            elif episode.dimension == "利润" and margin_extreme:
                score += 2
                reasons.append("该案例当时由利润维度的极端状态催生，与当前利润极端状态属于同一类型")
            if episode.mechanism == "资金布局型" and chip_triggered:
                score += 2
                reasons.append("该案例当时的催生机制是「资金布局型」，与当前检测到的筹码异常属于同一类型")

        if score >= MIN_MATCH_SCORE:
            scored.append({"case": case, "score": score, "score_label": _score_label(score), "reasons": reasons})
        elif score >= 1:
            below_threshold += 1

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n], below_threshold


def get_case_precedent_stats(case: Case):
    """
    给一条已经匹配上的历史案例，查一下它对应的"事前状态"在历史上同品种、同维度、
    持续天数量级相近的样本里，总共出现过多少次、其中多少次真的催生了事件——
    在对比图旁边给一句诚实的转化率，而不是让"形状很像"这种强视觉暗示单方面
    暗示"历史一定会重演"。找不到对应的 SetupEpisode（比如老案例数据没补这条）就
    如实返回 None，不硬凑。
    """
    episode = SetupEpisode.query.filter_by(led_to_case_id=case.id).first()
    if not episode or not episode.duration_days:
        return None

    lo, hi = episode.duration_days * 0.4, max(episode.duration_days * 2.5, 30)
    comparable = SetupEpisode.query.filter(
        SetupEpisode.variety_id == episode.variety_id,
        SetupEpisode.dimension == episode.dimension,
        SetupEpisode.duration_days >= lo,
        SetupEpisode.duration_days <= hi,
    ).all()
    if not comparable:
        return None

    led = [e for e in comparable if e.led_to_case_id]
    return {
        "dimension": episode.dimension,
        "mechanism": episode.mechanism,
        "comparable_count": len(comparable),
        "led_to_event_count": len(led),
        "base_rate": round(len(led) / len(comparable) * 100),
    }


def get_setup_episode_regions(variety: Variety, dimension="价格"):
    """
    把这个品种历史上所有"事前状态极端期"(SetupEpisode, 价格维度)取出来，给主K线图画成
    背景色块——正例(后来真的催生了案例)和反例(什么都没发生)用不同颜色区分。这样"历史上
    出现过2次类似极端状态、其中1次催生了事件、转化率约50%"这句话就不再是一句只能相信的
    文字，用户可以直接在K线图上看到"另外那一次没兑现的极端状态"具体是哪一段、后来怎么走的。
    """
    episodes = SetupEpisode.query.filter_by(variety_id=variety.id, dimension=dimension).all()
    regions = []
    for e in episodes:
        if not e.period_start:
            continue
        end = e.period_end or e.period_start
        regions.append({
            "start": e.period_start.isoformat(),
            "end": end.isoformat(),
            "led_to_case": e.led_to_case_id is not None,
            "mechanism": e.mechanism or "",
            "note": e.note or "",
            "case_id": e.led_to_case_id,
        })
    return regions


def _moving_average_series(values, window):
    """
    简单移动均线，只用"这天之前(含当天)"的数据算，不看未来——序列开头不够 window 天的
    地方给 None(诚实地留空，而不是拿不够的天数硬凑一个不准的均线出来)。
    """
    result = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
            continue
        segment = values[i + 1 - window : i + 1]
        if any(v is None for v in segment):
            result.append(None)
        else:
            result.append(round(sum(segment) / window, 2))
    return result


def get_case_comparison_series(variety: Variety, case: Case, lookback_days=30):
    """
    给一条"历史相似案例"生成能直接叠在一起看的归一化价格序列——不是简单地把两段K线摆在一起
    (两段绝对价格level不同、时间跨度不同，摆在一起没法比)，而是各自做百分比归一化，用同一个
    "day 0"对齐：
      历史案例：day 0 = 案例的 start_date(事件被市场注意到的那一天)，之前 lookback_days 天
                是"事前走势"，之后到 end_date 是"事件之后怎么走"。
      当前品种：day 0 = 最新交易日(今天)，之前 lookback_days 天是"现在的事前走势"，
                没有"之后"——因为还没发生，这正是对比的意义所在：如果现在这段形状和历史案例
                day 0 之前的形状很像，历史案例 day 0 之后的走势就是一个直观的参照。
    两条序列都以 day 0 当天收盘价为基准换算成百分比涨跌，这样在图上 x=0 处天然对齐、
    y=0 处也天然对齐，形状是否相似一眼就能看出来，不需要还原成绝对价格。
    """
    case_contract = _main_contract(case.variety)
    cur_contract = _main_contract(variety)
    if not case_contract or not cur_contract or not case.start_date:
        return None

    case_bars = DailyBar.query.filter_by(contract_id=case_contract.id).order_by(DailyBar.trade_date).all()
    cur_bars = DailyBar.query.filter_by(contract_id=cur_contract.id).order_by(DailyBar.trade_date).all()
    if not case_bars or not cur_bars:
        return None

    case_dates = [b.trade_date for b in case_bars]
    anchor_idx = next((i for i, d in enumerate(case_dates) if d >= case.start_date), None)
    if anchor_idx is None:
        return None

    end_idx = len(case_bars) - 1
    if case.end_date:
        end_idx = next((i for i, d in enumerate(case_dates) if d >= case.end_date), len(case_bars) - 1)

    # 均线要用"窗口开始之前"的历史也算进去，不能只拿截取出来的这一小段现算——不然显示窗口
    # 最左边那几根K线的均线会因为"看得到的天数不够"而失真。case_bars/cur_bars本来就是这个
    # 合约的完整历史，所以先在完整序列上把MA5/10/20都算好，最后再按显示窗口切片。
    case_closes_full = [b.close for b in case_bars]
    case_ma5_full = _moving_average_series(case_closes_full, 5)
    case_ma10_full = _moving_average_series(case_closes_full, 10)
    case_ma20_full = _moving_average_series(case_closes_full, 20)

    cur_closes_full = [b.close for b in cur_bars]
    cur_ma5_full = _moving_average_series(cur_closes_full, 5)
    cur_ma10_full = _moving_average_series(cur_closes_full, 10)
    cur_ma20_full = _moving_average_series(cur_closes_full, 20)

    start_idx = max(0, anchor_idx - lookback_days)

    # setup_start_date 是"极端状态真正开始"的时间点，通常比 start_date(事件被市场注意到
    # 的那天)早得多——这正是"事件是滞后确认"这个判断的核心论据，但之前这个字段只在文字里
    # 出现过，从没在图上标过。这里如果 setup_start_date 比默认的回看窗口还早，就把窗口
    # 往前延伸，确保这个"提前量"能在图上真的看到，而不是被回看天数直接截掉。
    setup_offset = None
    if case.setup_start_date:
        setup_idx = next((i for i, d in enumerate(case_dates) if d >= case.setup_start_date), None)
        if setup_idx is not None:
            start_idx = min(start_idx, setup_idx)
            setup_offset = setup_idx - anchor_idx

    # 案例本身的关键节点时间线(CaseTimeline: 预期炒作期/情绪消退期/现实回归期...)之前只在
    # 案例详情页以文字形式存在，对比图上完全看不到"如果形状像，历史上大概会经历哪几个阶段"。
    # 这里换算成同一套 offset 坐标，跟价格线画在一起。
    timeline_markers = []
    for tl in case.timeline:
        tl_idx = next((i for i, d in enumerate(case_dates) if d >= tl.event_date), None)
        if tl_idx is not None:
            timeline_markers.append({
                "offset": tl_idx - anchor_idx,
                "date": tl.event_date.isoformat(),
                "stage": tl.stage or "",
                "description": tl.description or "",
                "price": tl.price,
            })

    anchor_price = case_bars[anchor_idx].close
    case_series = [
        {"offset": i - anchor_idx, "date": case_bars[i].trade_date.isoformat(),
         "open": case_bars[i].open, "close": case_bars[i].close,
         "low": case_bars[i].low, "high": case_bars[i].high,
         "volume": case_bars[i].volume or 0, "open_interest": case_bars[i].open_interest or 0,
         "ma5": case_ma5_full[i], "ma10": case_ma10_full[i], "ma20": case_ma20_full[i],
         "pct": round((case_bars[i].close - anchor_price) / anchor_price * 100, 2)}
        for i in range(start_idx, end_idx + 1)
    ]

    cur_anchor_idx = len(cur_bars) - 1
    cur_start_idx = max(0, cur_anchor_idx - lookback_days)
    cur_anchor_price = cur_bars[cur_anchor_idx].close
    current_series = [
        {"offset": i - cur_anchor_idx, "date": cur_bars[i].trade_date.isoformat(),
         "open": cur_bars[i].open, "close": cur_bars[i].close,
         "low": cur_bars[i].low, "high": cur_bars[i].high,
         "volume": cur_bars[i].volume or 0, "open_interest": cur_bars[i].open_interest or 0,
         "ma5": cur_ma5_full[i], "ma10": cur_ma10_full[i], "ma20": cur_ma20_full[i],
         "pct": round((cur_bars[i].close - cur_anchor_price) / cur_anchor_price * 100, 2)}
        for i in range(cur_start_idx, cur_anchor_idx + 1)
    ]

    return {
        "case_series": case_series,
        "current_series": current_series,
        "case_variety_name": f"{case.variety.name}（{case.variety.code}）",
        "setup_offset": setup_offset,
        "timeline_markers": timeline_markers,
    }


def get_case_risk_reward(comparison):
    """
    把"历史相似案例"的价格路径提炼成交易员真正要的三个数字：从锚点(day 0，也就是
    "现在"对应的那个位置)往后，历史上走出过的最大涨幅、最大回撤、最终涨跌幅、
    以及用了多少个交易日。这三个数字全部来自 get_case_comparison_series 已经算好的
    真实历史价格路径(pct 是相对锚点收盘价的百分比涨跌)，不是另外拍脑袋给的止损/止盈——
    这也是为什么不单独接收 case 参数，而是直接吃 comparison 的结果，避免在这里重新
    计算一遍价格路径导致两处口径不一致。
    是不是"逻辑没兑现"的失败案例(is_failure_case)这里刻意不做特殊处理——价格路径本身
    已经如实反映了"到底涨了还是跌了"，如果逻辑没兑现，走出来的大概率就是一个很小的
    涨跌幅或者跟预期相反的方向，不需要再额外根据案例标签去调整这几个数字，那样反而是
    用一个判断去覆盖另一个已经算出来的事实。
    """
    if not comparison:
        return None
    after_anchor = [b for b in comparison["case_series"] if b["offset"] >= 0]
    if len(after_anchor) < 2:
        return None

    pct_values = [b["pct"] for b in after_anchor]
    return {
        "max_gain_pct": max(pct_values),
        "max_drawdown_pct": min(pct_values),
        "final_pct": after_anchor[-1]["pct"],
        "duration_days": after_anchor[-1]["offset"],
    }


def db_or_same_variety_or_shared_tag(variety, hot_factor_ids):
    """构造一个宽松的候选集过滤条件：同品种的案例，或者驱动因素与当前激活因素重合的案例。"""
    from sqlalchemy import or_

    conditions = [Case.variety_id == variety.id]
    if hot_factor_ids:
        conditions.append(Case.event_type_id.in_(hot_factor_ids))
    return or_(*conditions)


def _percentile_rank(series, value):
    """value 在 series 里的百分位排名（0-100），用于价格/持仓的历史分位计算。"""
    if not series or value is None:
        return None
    sorted_series = sorted(series)
    n = len(sorted_series)
    below = sum(1 for v in sorted_series if v <= value)
    return round(below / n * 100)


# ---------------------------------------------------------------------------
# 事前状态信号：把"事件发生后怎么走"往前挪到"什么样的环境容易催生这个事件"
# ---------------------------------------------------------------------------
#
# 很多事件不是随机外生冲击，而是价格/筹码/基本面走到极端后被动"挤"出来的结果——
# 内幕资金提前布局、物极必反、行业痛到政策不得不出手，这三种情况共同的特征是：
# 由此产生的行情往往在"事件"被大众看到之前就已经走了一部分，等看到新闻再反应就晚了。
# 这里落地两件事：
#   1. 不依赖任何具体新闻，只用价格自身的历史百分位，判断现在是不是已经处于
#      historically "容易催生事件"的极端状态，以及这个极端状态已经持续了多久。
#   2. 拿这个"持续天数"去匹配 SetupEpisode 历史库——库里既有"后来真的催生了事件"
#      的正例，也刻意保留了"同样极端但什么都没发生"的反例，算出一个诚实的基础
#      转化率，而不是暗示"极端了就一定会有事发生"。

SETUP_MIN_WINDOW = 60  # 至少要有60个交易日数据才开始计算"扩展窗口百分位"，避免样本太少失真


def _expanding_percentile_series(closes, min_window=SETUP_MIN_WINDOW):
    """
    逐日计算"只用当天及之前的数据"算出的历史百分位，而不是拿整段历史（包含未来数据）
    去评价过去某一天——用未来数据判断过去处在什么分位是一种看未来的偏差，这里刻意避免。
    前 min_window 天数据不够时该天返回 None。
    """
    results = [None] * len(closes)
    for i in range(len(closes)):
        if i < min_window or closes[i] is None:
            continue
        window_slice = [v for v in closes[: i + 1] if v is not None]
        results[i] = _percentile_rank(window_slice, closes[i])
    return results


def compute_setup_signal(variety: Variety):
    """
    现在这个位置本身，是不是历史上容易催生"催生型事件"的环境：
    价格是否处于历史极端分位（<=10% 或 >=90%），如果是，已经连续处于这个极端多少天了。
    这不判断"会不会真的发生什么"，只是把"现在像不像一个历史上常见的事前状态"量化出来。
    """
    contract = _main_contract(variety)
    if not contract:
        return None
    bars = DailyBar.query.filter_by(contract_id=contract.id).order_by(DailyBar.trade_date).all()
    closes = [b.close for b in bars if b.close is not None]
    if len(closes) <= SETUP_MIN_WINDOW:
        return None

    pct_series = _expanding_percentile_series(closes)
    latest_pct = pct_series[-1]
    if latest_pct is None:
        return None

    is_low = latest_pct <= 10
    is_high = latest_pct >= 90
    in_extreme_zone = is_low or is_high

    streak = 0
    if in_extreme_zone:
        for p in reversed(pct_series):
            if p is None:
                break
            if (is_low and p <= 10) or (is_high and p >= 90):
                streak += 1
            else:
                break

    return {
        "latest_date": bars[-1].trade_date,
        "latest_percentile": latest_pct,
        "direction": "低位" if is_low else ("高位" if is_high else "中性"),
        "in_extreme_zone": in_extreme_zone,
        "streak_days": streak,
    }


def match_setup_precedents(variety: Variety, setup_signal, dimension="价格", top_n=5):
    """
    拿"现在已经在极端状态里待了多久"去匹配历史 SetupEpisode，返回一个包含正例和反例的
    诚实转化率，而不是只挑"后来真的催生了事件"的案例出来、制造必然反转的错觉。
    找不到可比的历史episode时也如实说明，不强行凑数。
    dimension 区分是在"价格"还是"利润"这个维度上的极端——两者不能混着匹配，
    价格极端持续60天和利润极端持续60天不是一回事。
    """
    if not setup_signal or not setup_signal["in_extreme_zone"]:
        return None

    episodes = (
        SetupEpisode.query.filter_by(variety_id=variety.id, dimension=dimension)
        .order_by(SetupEpisode.period_start.desc())
        .all()
    )
    if not episodes:
        return {"comparable_count": 0, "led_to_event_count": 0, "base_rate": None, "episodes": []}

    streak = max(setup_signal["streak_days"], 1)
    lo, hi = streak * 0.4, max(streak * 2.5, 30)
    comparable = [e for e in episodes if e.duration_days and lo <= e.duration_days <= hi]
    used_fallback = False
    if not comparable:
        comparable = episodes  # 严格分桶匹配不到时，把全部历史episode拿出来，并标注这是放宽后的结果
        used_fallback = True

    led_to_event = [e for e in comparable if e.led_to_case_id]
    base_rate = round(len(led_to_event) / len(comparable) * 100) if comparable else None

    return {
        "comparable_count": len(comparable),
        "led_to_event_count": len(led_to_event),
        "base_rate": base_rate,
        "used_fallback": used_fallback,
        "episodes": comparable[:top_n],
    }


# ---------------------------------------------------------------------------
# 利润/成本维度的事前状态——独立于价格分位数
# ---------------------------------------------------------------------------
#
# 价格没有处于历史极端，不代表基本面没有走极端：成本端变化可能让利润率在价格中性的
# 位置就已经跌破历史盈亏底线。这里用同样的"扩展窗口百分位+连续天数"逻辑，但换成
# 月度利润率序列，作为一个完全独立于价格的判断维度。

MARGIN_MIN_WINDOW = 12  # 至少12个月的利润率数据才开始判断，月度数据本来就稀疏，窗口不能设太大


def compute_margin_signal(variety: Variety):
    """
    利润率是否处于历史极端（且价格不一定同时极端）——避免只用价格分位数代理基本面松紧，
    这条通道专门捕捉"价格看着还行，利润已经历史最差"这种容易被价格维度漏掉的情况。
    """
    records = (
        ProfitMarginRecord.query.filter_by(variety_id=variety.id).order_by(ProfitMarginRecord.period).all()
    )
    values = [r.margin_value for r in records if r.margin_value is not None]
    if len(values) <= MARGIN_MIN_WINDOW:
        return None

    pct_series = _expanding_percentile_series(values, min_window=MARGIN_MIN_WINDOW)
    latest_pct = pct_series[-1]
    if latest_pct is None:
        return None

    is_low = latest_pct <= 10
    is_high = latest_pct >= 90
    in_extreme_zone = is_low or is_high

    streak = 0
    if in_extreme_zone:
        for p in reversed(pct_series):
            if p is None:
                break
            if (is_low and p <= 10) or (is_high and p >= 90):
                streak += 1
            else:
                break

    return {
        "latest_period": records[-1].period,
        "latest_percentile": latest_pct,
        "latest_value": records[-1].margin_value,
        "direction": "利润极低" if is_low else ("利润极高" if is_high else "中性"),
        "in_extreme_zone": in_extreme_zone,
        "streak_months": streak,
        # 复用和价格一样的天数分桶匹配逻辑，把月折算成天，避免另外写一套匹配函数
        "streak_days": streak * 30,
    }


# ---------------------------------------------------------------------------
# 筹码异常信号（资金布局型）——刻意不依赖价格分位数，任何价格位置都要检查
# ---------------------------------------------------------------------------
#
# 资金布局型的核心特征就是"跟价格所处位置没有必然关系"：内幕/嗅觉资金什么价位都能
# 提前动作。之前把这类信号跟价格极值开关绑在一起是逻辑错误，这里独立出来，任何时候
# 都检查一遍持仓量变化率、仓单变化率、虚实盘比这几个跟价格位置无关的筹码指标。

CHIP_LOOKBACK_DAYS = 20  # 用最近20个交易日的变化率去和历史同期变化率分布比较


def compute_chip_anomaly_signal(variety: Variety):
    """
    不看价格在哪，只看筹码本身像不像历史上"资金已经在提前动作"的样子：
    持仓量短期变化率、仓单短期变化率是否处于历史极端，虚实盘比是否超过警戒阈值。
    命中任意一条就标记为"检测到筹码异常"，具体原因分别列出，方便自己判断可信度。
    """
    contract = _main_contract(variety)
    if not contract:
        return None

    pos_rows = PositionRank.query.filter_by(contract_id=contract.id).order_by(PositionRank.trade_date).all()
    wh_rows = WarehouseReceipt.query.filter_by(contract_id=contract.id).order_by(WarehouseReceipt.trade_date).all()
    if len(pos_rows) <= CHIP_LOOKBACK_DAYS * 3:
        return None

    reasons = []
    # oi_direction 只标"活跃度异常"，不进复合信号的多空投票——持仓量变化本身不带方向
    # （新多和新空都会让它变大），强行给它安个多空标签是过度解读；wh_direction 和下面新加的
    # top5_direction 才有明确的经济学方向，所以只有这两个会被 compute_composite_signal
    # 采纳为投票（wh_direction：仓单是可交割的现货库存，变多=供应压力变松→偏空，变少=现货
    # 变紧→偏多；top5_direction：见下面的详细注释）。
    oi_direction = None
    wh_direction = None

    oi_series = [p.total_open_interest for p in pos_rows if p.total_open_interest]
    oi_roc_series = _rate_of_change_series(oi_series, CHIP_LOOKBACK_DAYS)
    oi_roc_pct = _expanding_percentile_series(oi_roc_series, min_window=CHIP_LOOKBACK_DAYS * 2)
    if oi_roc_pct and oi_roc_pct[-1] is not None and (oi_roc_pct[-1] >= 95 or oi_roc_pct[-1] <= 5):
        oi_direction = "异常放大" if oi_roc_pct[-1] >= 95 else "异常萎缩"
        reasons.append(f"最近{CHIP_LOOKBACK_DAYS}个交易日持仓量变化率{oi_direction}，处于历史{oi_roc_pct[-1]}%分位")

    wh_series = [w.receipt_qty for w in wh_rows if w.receipt_qty is not None]
    wh_roc_series = _rate_of_change_series(wh_series, CHIP_LOOKBACK_DAYS)
    wh_roc_pct = _expanding_percentile_series(wh_roc_series, min_window=CHIP_LOOKBACK_DAYS * 2)
    if wh_roc_pct and wh_roc_pct[-1] is not None and (wh_roc_pct[-1] >= 95 or wh_roc_pct[-1] <= 5):
        wh_direction = "骤增" if wh_roc_pct[-1] >= 95 else "骤减"
        reasons.append(f"最近{CHIP_LOOKBACK_DAYS}个交易日仓单{wh_direction}，变化率处于历史{wh_roc_pct[-1]}%分位")

    if oi_series and wh_series and wh_series[-1]:
        ratio = oi_series[-1] / wh_series[-1]
        if ratio > 100:
            reasons.append(f"虚实盘比达到{round(ratio, 1)}:1，超过100:1警戒阈值")

    # --- 前5席位多空集中度差值：2026-08新加的第三条筹码维度 -----------------------------
    # PositionRank 表里本来就有 top5_long_ratio / top5_short_ratio（持仓龙虎榜前5大席位的
    # 多头/空头占比）这两个字段，录数据的时候一直有填，但在这条新逻辑加进来之前，从来没有
    # 任何分析函数读取过它们——等于一直有数据白白放着没用。
    #
    # 之所以专门把它做成第三条独立维度、而不是并进 oi_direction：总持仓量变化率不带方向
    # （前面注释解释过），但"前5大席位里，多头占比比空头占比高多少"是有方向的——持仓量最大
    # 的那批资金一般被认为资金/信息优势更强，他们的多空集中度整体往哪边倾斜，比总持仓量的
    # 涨跌更接近"主力在做什么"，所以这条允许直接投票，跟 wh_direction 同等对待。
    #
    # 判断分两层，跟 oi/仓单那两条的方法保持一致（复用同一套 _expanding_percentile_series /
    # _rate_of_change_series 工具函数，不是另起一套逻辑）：
    #   1) 先看"差值本身现在处于历史什么水平"——这是最直接的判断，衡量"现在前排资金的
    #      多空集中度，跟历史比是不是罕见地偏向一边"。
    #   2) 如果差值本身还没到历史极值，但可能正在快速往一个方向变化（比如从中性快速转向
    #      净多，但还没来得及积累到历史极端水平），再看它最近 CHIP_LOOKBACK_DAYS 天的
    #      变化率是否处于历史极端——这条能捕捉"还没到极值、但短期内变化很快"的情况，
    #      跟 oi_direction/wh_direction 用的是同一套变化率+分位数方法。
    #   两层只要有一层触发就采纳，层1判断不了才看层2，不会同时看两层导致方向自相矛盾。
    top5_direction = None
    top5_level_percentile = None
    top5_roc_percentile = None
    top5_series = [
        (p.top5_long_ratio - p.top5_short_ratio)
        for p in pos_rows
        if p.top5_long_ratio is not None and p.top5_short_ratio is not None
    ]
    top5_level_pct_series = _expanding_percentile_series(top5_series, min_window=CHIP_LOOKBACK_DAYS * 2)
    if top5_level_pct_series and top5_level_pct_series[-1] is not None and (
        top5_level_pct_series[-1] >= 95 or top5_level_pct_series[-1] <= 5
    ):
        top5_level_percentile = top5_level_pct_series[-1]
        top5_direction = "集中度历史性偏多" if top5_level_percentile >= 95 else "集中度历史性偏空"
        reasons.append(
            f"前5席位多空集中度差值（多头占比-空头占比）处于历史{top5_level_percentile}%分位，"
            f"{'多头' if top5_level_percentile >= 95 else '空头'}集中度历史罕见地高"
        )
    else:
        top5_roc_series = _rate_of_change_series(top5_series, CHIP_LOOKBACK_DAYS)
        top5_roc_pct_series = _expanding_percentile_series(top5_roc_series, min_window=CHIP_LOOKBACK_DAYS * 2)
        if top5_roc_pct_series and top5_roc_pct_series[-1] is not None and (
            top5_roc_pct_series[-1] >= 95 or top5_roc_pct_series[-1] <= 5
        ):
            top5_roc_percentile = top5_roc_pct_series[-1]
            top5_direction = "集中度快速转多" if top5_roc_percentile >= 95 else "集中度快速转空"
            reasons.append(
                f"前5席位多空集中度差值最近{CHIP_LOOKBACK_DAYS}个交易日变化率处于历史"
                f"{top5_roc_percentile}%分位，短期内快速{'转向多头' if top5_roc_percentile >= 95 else '转向空头'}"
            )

    return {
        "triggered": bool(reasons),
        "reasons": reasons,
        "oi_direction": oi_direction,
        "wh_direction": wh_direction,
        "top5_direction": top5_direction,
        "top5_level_percentile": top5_level_percentile,
        "top5_roc_percentile": top5_roc_percentile,
        "note": "这条通道不看价格所处位置，任何时候检测到都会提示——资金提前布局跟价格高低没有必然关系。",
    }


def _rate_of_change_series(series, window):
    """逐点计算相对window天前的变化率，用来判断筹码指标是不是短期内异常放大/萎缩。"""
    result = [None] * len(series)
    for i in range(len(series)):
        if i < window or not series[i - window]:
            continue
        result[i] = (series[i] - series[i - window]) / abs(series[i - window])
    return result


# ---------------------------------------------------------------------------
# 决策参考：把价格/利润/筹码/历史案例四路独立信号的方向摆在一起对齐
# ---------------------------------------------------------------------------
#
# 前面几条通道(setup_signal/margin_signal/chip_signal/match_historical_cases)各自
# 独立算完就结束了，页面上是四张互不相干的卡片，"到底该偏多偏空"这一步一直是交易员
# 自己在脑子里把四个数字加权。这里补的不是一个"更聪明的预测模型"——真要有那种模型
# 也不该是这几行规则代码能实现的——而是一个"信号对齐清单"：把每一路已经算出来的方向
# 摆在一起，数有几路一致、有没有互相打架，给一个措辞克制的结论(多头因素占优/空头因素
# 占优/信号不一致/无明显方向)，而不是伪装成一个精确到小数点的"多空评分"。
# 这依然不是预测，是替你把"要不要自己动手汇总这四个数字"这一步省掉，最终判断和风险
# 仍然由使用者自己承担——这一点在返回结果里的 caveat 字段里也如实写出来，不能省略。


def compute_composite_signal(setup_signal, margin_signal, chip_signal, matched_cases):
    """
    汇总价格分位、利润状态、筹码/仓单方向、历史相似案例这四路独立信号的方向，
    给一个"多头因素占优 / 空头因素占优 / 多空信号不一致 / 无明显方向"的结论。

    每一路的方向判断逻辑（都是简单、可解释、能一眼看懂"为什么这么判"的启发式，
    不是黑箱模型）：
    - 价格分位：处于历史低位 -> 均值回归意义上偏多；处于历史高位 -> 偏空。
    - 利润状态：利润极低 -> 现金成本对价格下方有支撑，偏多；利润极高 -> 超额利润
      吸引扩产/挤压后续涨幅，偏空。
    - 筹码/仓单：仓单方向投票(骤增=可交割货源变松=偏空，骤减=变紧=偏多)，以及
      2026-08新加的前5席位多空集中度方向投票(集中度偏多/快速转多=偏多，反之=偏空)——
      这两条分开独立投票，谁触发算谁的，互不覆盖。持仓量变化率异常本身不投票，因为
      持仓量变大不带方向(新多新空都会让它变大)，强行安一个多空标签是过度解读，这里
      保持克制。
    - 历史相似案例：按每条案例的匹配分加权，看这些案例最终价格走势(price_end 相对
      price_start)平均偏向哪个方向；不因为案例标了"逻辑未兑现"就跳过或反向处理，
      因为 price_start/price_end 本身已经如实记录了实际发生的涨跌，是不是"未兑现"
      只是叙事层面的标签，不应该覆盖已经发生的价格事实。
    """
    components = []
    votes = []

    if setup_signal and setup_signal.get("in_extreme_zone"):
        if setup_signal["direction"] == "低位":
            votes.append(1)
            lean = "偏多（均值回归逻辑：历史低位区间之后价格更常见的是修复而非持续破位）"
        else:
            votes.append(-1)
            lean = "偏空（均值回归逻辑：历史高位区间之后价格更常见的是回落而非持续冲高）"
        components.append({
            "channel": "价格分位",
            "read": f"历史{setup_signal['latest_percentile']}%分位（{setup_signal['direction']}），已持续{setup_signal['streak_days']}个交易日",
            "lean": lean,
        })
    else:
        components.append({"channel": "价格分位", "read": "不处于历史极端区间（10%~90%之间）", "lean": "中性，不投票"})

    if margin_signal and margin_signal.get("in_extreme_zone"):
        if margin_signal["direction"] == "利润极低":
            votes.append(1)
            lean = "偏多（现金成本支撑逻辑：亏损持续越久，减停产压力越大，向下空间受限）"
        else:
            votes.append(-1)
            lean = "偏空（超额利润逻辑：利润过高通常吸引扩产/复产，后续涨幅容易被压制）"
        components.append({
            "channel": "利润状态",
            "read": f"历史{margin_signal['latest_percentile']}%分位（{margin_signal['direction']}），已持续{margin_signal['streak_months']}个月",
            "lean": lean,
        })
    else:
        components.append({"channel": "利润状态", "read": "不处于历史极端区间", "lean": "中性，不投票"})

    if chip_signal and chip_signal.get("triggered"):
        wh_direction = chip_signal.get("wh_direction")
        top5_direction = chip_signal.get("top5_direction")
        chip_voted = False

        if wh_direction == "骤增":
            votes.append(-1)
            chip_voted = True
            components.append({"channel": "筹码/仓单", "read": "仓单短期骤增，可交割货源变宽松", "lean": "偏空（供应压力逻辑）"})
        elif wh_direction == "骤减":
            votes.append(1)
            chip_voted = True
            components.append({"channel": "筹码/仓单", "read": "仓单短期骤减，可交割货源收紧", "lean": "偏多（现货偏紧逻辑）"})

        # 前5席位多空集中度：独立于仓单的第二条筹码投票渠道，用的是 PositionRank 表里
        # top5_long_ratio/top5_short_ratio 算出来的差值（见 compute_chip_anomaly_signal
        # 里的详细注释）。跟仓单方向分开判断、分开投票，两条谁触发算谁的，不会互相覆盖，
        # 也可能同时触发（这种时候两票方向一致会加强一致性，方向不一致就如实算成分歧）。
        if top5_direction in ("集中度历史性偏多", "集中度快速转多"):
            votes.append(1)
            chip_voted = True
            pct = chip_signal.get("top5_level_percentile") or chip_signal.get("top5_roc_percentile")
            components.append({
                "channel": "筹码/前5席位集中度",
                "read": f"{top5_direction}（历史{pct}%分位）",
                "lean": "偏多（前排资金——一般被认为资金/信息优势更强——净多集中度偏高，跟随大资金方向逻辑）",
            })
        elif top5_direction in ("集中度历史性偏空", "集中度快速转空"):
            votes.append(-1)
            chip_voted = True
            pct = chip_signal.get("top5_level_percentile") or chip_signal.get("top5_roc_percentile")
            components.append({
                "channel": "筹码/前5席位集中度",
                "read": f"{top5_direction}（历史{pct}%分位）",
                "lean": "偏空（前排资金净空集中度偏高，跟随大资金方向逻辑）",
            })

        if not chip_voted:
            # 只有持仓量变化率异常触发，仓单和前5席位集中度都没触发方向：不投票，但如实
            # 提示，别把这条信息藏起来
            components.append({
                "channel": "筹码/持仓量",
                "read": "、".join(chip_signal["reasons"]),
                "lean": "方向不明，仅提示可能有资金提前布局，不计入下面的多空对齐，需结合其他信号自行判断",
            })
    else:
        components.append({"channel": "筹码", "read": "未检测到异常", "lean": "中性，不投票"})

    case_reads = []
    case_vote_weight = 0.0
    case_weight_total = 0
    for m in (matched_cases or []):
        case = m["case"]
        if case.price_start and case.price_end:
            pct_move = round((case.price_end - case.price_start) / case.price_start * 100, 1)
            case_reads.append(f"{case.name}（{pct_move:+.1f}%）")
            case_vote_weight += (1 if pct_move > 0 else (-1 if pct_move < 0 else 0)) * m["score"]
            case_weight_total += m["score"]

    if case_weight_total > 0:
        avg = case_vote_weight / case_weight_total
        if avg > 0.3:
            votes.append(1)
            lean = "偏多（匹配到的历史案例最终多数是上涨）"
        elif avg < -0.3:
            votes.append(-1)
            lean = "偏空（匹配到的历史案例最终多数是下跌）"
        else:
            lean = "涨跌互现，方向不一致，不计入对齐"
        components.append({
            "channel": "历史相似案例",
            "read": f"{len(case_reads)}个匹配案例的实际走势：" + "、".join(case_reads),
            "lean": lean,
        })
    else:
        components.append({"channel": "历史相似案例", "read": "没有匹配到有方向性参考的历史案例", "lean": "中性，不投票"})

    bullish = sum(1 for v in votes if v > 0)
    bearish = sum(1 for v in votes if v < 0)

    # votes 里最多可能有5票：价格分位、利润状态、筹码/仓单、筹码/前5席位集中度（2026-08新加）、
    # 历史相似案例。2026-08之前筹码这条只有仓单一票能投，那时候最多4票，"高置信度"的门槛定
    # 在">=3票同向"；现在筹码拆成仓单+前5席位集中度两条独立投票渠道，最多可以到5票，所以把
    # "高置信度"的门槛同步提到">=4票同向"，避免门槛没跟着调整、让"高"变得比原来更容易触发。
    # 注意仓单和前5席位集中度都属于"筹码"这个大类，两者背后的资金/库存动态可能本来就相关，
    # 不是完全独立的信息来源，这也是为什么门槛要提高而不是维持不变——见 docs/system_design.md
    # 第5节的详细说明。
    if bullish == 0 and bearish == 0:
        verdict, confidence = "无明显方向", "低"
        summary = "价格、利润、筹码/仓单、筹码/前5席位集中度、历史案例这几路信号目前都不处于极端或方向不一致，没有形成合力，建议观望，不强行找方向。"
    elif bullish > 0 and bearish > 0:
        verdict, confidence = "多空信号不一致", "低"
        summary = f"{bullish}路信号偏多、{bearish}路信号偏空，出现分歧——这种时候历史经验是不宜重仓单边，观望或降低仓位等信号收敛更稳妥。"
    elif bullish > bearish:
        verdict = "多头因素占优"
        confidence = "高" if bullish >= 4 else "中"
        summary = f"{bullish}路独立信号同时指向偏多方向，暂无信号指向偏空，一致性{'较高' if bullish >= 4 else '中等'}。"
    else:
        verdict = "空头因素占优"
        confidence = "高" if bearish >= 4 else "中"
        summary = f"{bearish}路独立信号同时指向偏空方向，暂无信号指向偏多，一致性{'较高' if bearish >= 4 else '中等'}。"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "components": components,
        "caveat": "这是历史统计意义上的方向对齐提示，基于规则打分和样本有限的历史数据，不构成投资建议，"
                  "不保证未来走势会重复历史，也不替代你自己对仓位和风险的判断。",
    }


def summarize_case_risk_reward(matched_cases):
    """
    把所有匹配到的历史案例各自的风险回报数字(get_case_risk_reward)汇总成一句话：
    历史相似情形下，价格大致在什么区间波动、最坏情况回撤多少、平均用了多少个交易日。
    这不是给出一个precise的止损/止盈点位建议——不同案例的最大涨幅/回撤差异可能很大，
    这里如实展示区间而不是取一个平均值掩盖分歧，避免看起来比实际更精确。
    """
    entries = [m["risk_reward"] for m in (matched_cases or []) if m.get("risk_reward")]
    if not entries:
        return None

    gains = [e["max_gain_pct"] for e in entries]
    drawdowns = [e["max_drawdown_pct"] for e in entries]
    durations = [e["duration_days"] for e in entries]
    return {
        "sample_count": len(entries),
        "gain_range": (min(gains), max(gains)),
        "drawdown_range": (min(drawdowns), max(drawdowns)),
        "duration_range": (min(durations), max(durations)),
    }


def get_macro_snapshot():
    """
    宏观环境参考快照：2026-08新加，把 MacroData 表里每个指标最新一期的读数摆出来，
    仅作为背景信息展示在页面上，**不参与** compute_composite_signal 的多空投票，
    也不影响 verdict/confidence 的计算结果——这一点很重要，别以后不小心把它接进投票逻辑
    却忘了这条注释。

    为什么故意不让它投票（而不是干脆不做），原因有三条，详细讨论见 docs/system_design.md
    第5节，这里简单记一下：
    1) 宏观指标对单个商品期货品种的传导本身复杂、滞后、非线性，不像价格分位/利润分位那样
       可以直接套用"历史分位数"这套简单规则给出可靠方向，勉强套用容易得出似是而非的结论；
    2) MacroData 目前样本量偏薄（每个指标基本是每月一个点，一共111条，覆盖不了几年），
       拿这么少的点去算"历史分位数"统计意义有限，跟案例库样本小是同一类问题；
    3) 现在也没有一张"哪个宏观指标该被哪个品种关注"的映射表——比如 PMI 对纯碱(建材类)
       和对豆粕(农产品类)这两个品种的含义、传导路径完全不同，不能一概而论地都拿来投票，
       贸然接入容易引入看着有道理、实际没被验证过的伪信号。
    所以现阶段的定位是：如实把最新数据摆出来，要不要纳入自己的判断，由你自己决定；
    等以后想清楚了映射关系、也攒够了年份跨度的数据，再考虑要不要把它升级成能投票的信号，
    到时候可以参照 compute_setup_signal 那一套"分位数+持续时长"的写法。
    """
    indicator_names = sorted(
        row[0] for row in MacroData.query.with_entities(MacroData.indicator).distinct().all()
    )
    snapshot = []
    for name in indicator_names:
        rows = (
            MacroData.query.filter_by(indicator=name)
            .order_by(MacroData.report_date.desc())
            .limit(2)
            .all()
        )
        if not rows:
            continue
        latest = rows[0]
        prev = rows[1] if len(rows) > 1 else None
        trend = None
        if prev is not None and prev.value is not None and latest.value is not None:
            if latest.value > prev.value:
                trend = "较上期上升"
            elif latest.value < prev.value:
                trend = "较上期下降"
            else:
                trend = "与上期持平"
        snapshot.append({
            "indicator": name,
            "value": latest.value,
            "report_date": latest.report_date,
            "trend": trend,
        })
    return snapshot
