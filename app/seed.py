# -*- coding: utf-8 -*-
"""
测试数据生成脚本
================
目标不是"数据真实"，是"数据自洽、能让分析引擎和页面把完整链路跑起来"：
K线要能画、事件要能标注在K线上、持仓/仓单要能算出虚实盘比、案例要能被检索匹配到。

后续接爬虫/数据商之后，只需要把这里生成数据的部分换成真实数据源，模型结构、
分析引擎、页面完全不用动——这是先做假数据骨架的意义。

行情走势不是纯随机游走：每个案例都会在对应的时间窗口里，把价格"整形"成
"从起点冲向极值、再回落到终点"的路径，这样案例库和K线图才是互相呼应的，
而不是案例文字描述一套、图上完全看不出来另一套。
"""
import math
import random
from datetime import date, timedelta

from app.extensions import db
from app.models import (
    Variety,
    FactorTag,
    VarietyFactor,
    Contract,
    DailyBar,
    PositionRank,
    WarehouseReceipt,
    Basis,
    Case,
    CaseTimeline,
    Event,
    MacroData,
    Policy,
    SetupEpisode,
    ProfitMarginRecord,
    ProductionRoute,
    SupplyChainNode,
)

END_DATE = date(2026, 8, 10)
START_DATE = END_DATE - timedelta(days=365 * 3)  # 约3年测试数据


def trading_dates(start, end):
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 只简单跳过周末，不处理节假日，测试数据够用
            dates.append(d)
        d += timedelta(days=1)
    return dates


def build_price_path(dates, base_price, daily_vol, seed, case_windows):
    """
    生成一条价格路径：底层是围绕 base_price 的均值回归随机游走，
    再把每个 case_window（起点日/极值日/终点日/起点价/极值价/终点价）对应的区间，
    整形成一条"冲高/探底再回落"的路径叠加上去，保证图和案例叙述对得上。
    """
    rng = random.Random(seed)
    n = len(dates)
    prices = [base_price] * n
    price = base_price
    for i in range(n):
        # 均值回归 + 随机扰动
        price += (base_price - price) * 0.01 + rng.gauss(0, daily_vol)
        price = max(price, base_price * 0.3)
        prices[i] = price

    date_index = {d: i for i, d in enumerate(dates)}

    for win in case_windows:
        s_idx = _nearest_index(date_index, dates, win["start_date"])
        e_idx = _nearest_index(date_index, dates, win["end_date"])
        if s_idx is None or e_idx is None or e_idx <= s_idx:
            continue
        mid_idx = s_idx + max(1, (e_idx - s_idx) // 3)  # 冲高/探底点大约在前1/3处，符合"预期炒作期短、回归期长"的规律
        _ramp(prices, s_idx, mid_idx, win["price_start"], win["price_extreme"], daily_vol, rng)
        _ramp(prices, mid_idx, e_idx, win["price_extreme"], win["price_end"], daily_vol, rng)

    return prices


def _nearest_index(date_index, dates, target_date):
    if target_date in date_index:
        return date_index[target_date]
    for i, d in enumerate(dates):
        if d >= target_date:
            return i
    return None


def _ramp(prices, start_idx, end_idx, start_val, end_val, vol, rng):
    span = max(1, end_idx - start_idx)
    for i in range(start_idx, min(end_idx + 1, len(prices))):
        t = (i - start_idx) / span
        prices[i] = start_val + (end_val - start_val) * t + rng.gauss(0, vol * 0.6)


def run_seed():
    if Variety.query.first() is not None:
        return  # 已经有数据了，不重复灌入

    factor_tags = _seed_factor_tags()
    varieties = _seed_varieties()
    _seed_variety_factors(varieties, factor_tags)
    _seed_production_and_supply_chain(varieties)

    dates = trading_dates(START_DATE, END_DATE)

    sa_cases = _sa_case_defs()
    fg_cases = _fg_case_defs()
    m_cases = _m_case_defs()

    # wh_base 相对 oi_base 调高过，让正常情况下虚实盘比落在30-40:1左右，不会常年顶着100:1警戒线，
    # 这样警戒线才是一个真正稀有、有信息量的信号，而不是每个品种永远都在报警。
    _seed_market_data(varieties["SA"], dates, base_price=1650, daily_vol=18, seed=101, case_windows=sa_cases,
                       oi_base=380000, wh_base=11000)
    _seed_market_data(varieties["FG"], dates, base_price=1150, daily_vol=14, seed=202, case_windows=fg_cases,
                       oi_base=650000, wh_base=18000)
    _seed_market_data(varieties["M"], dates, base_price=3050, daily_vol=22, seed=303, case_windows=m_cases,
                       oi_base=1450000, wh_base=35000)

    sa_created = _seed_cases(varieties["SA"], sa_cases, factor_tags)
    fg_created = _seed_cases(varieties["FG"], fg_cases, factor_tags)
    m_created = _seed_cases(varieties["M"], m_cases, factor_tags)

    _seed_setup_episodes(varieties["SA"], sa_cases, sa_created)
    _seed_setup_episodes(varieties["FG"], fg_cases, fg_created)
    _seed_setup_episodes(varieties["M"], m_cases, m_created)
    _seed_negative_setup_episodes(varieties)

    # 利润/成本维度的事前状态——独立于价格，玻璃这里故意设计成"价格不极端、利润已极端"
    _seed_margin_series(varieties)
    _seed_margin_setup_episodes(varieties, fg_created)

    # 筹码异常（资金布局型）——独立于价格，豆粕这里故意设计成"价格不极端、仓单骤减"
    _inject_recent_chip_anomaly(varieties["M"])

    _seed_recent_events(varieties, factor_tags)
    _seed_macro_and_policy()

    db.session.commit()


def _seed_factor_tags():
    defs = [
        ("政策喊话反内卷", "宏观", "产业政策层面的表态/会议提法，尚无具体落地措施，通常是脉冲式影响"),
        ("产能治理落地", "供应端", "具体的限产/去产能/环保督察等已发布的措施文件"),
        ("产能检修", "供应端", "计划内/计划外的装置检修，影响短期供应"),
        ("天气异常", "供应端", "干旱、洪涝、寒潮等影响产量或运输的天气事件"),
        ("进口收紧", "供应端", "进口政策、关税、检验检疫等导致进口收紧"),
        ("地产需求", "需求端", "地产新开工/竣工/销售数据变化带来的下游需求变化"),
        ("下游开工", "需求端", "加工/深加工环节开工率变化"),
        ("出口需求", "需求端", "海外订单、出口政策变化带来的需求变化"),
        ("汇率波动", "宏观", "人民币汇率大幅波动影响进口成本或跨市场套利"),
        ("供需突变", "供应端", "库存、产量、需求出现明显超预期的变化，改变原有平衡"),
        ("逼仓行情", "宏观", "多空一方通过资金优势主导盘面，脱离现货基本面定价"),
    ]
    tags = {}
    for name, category, desc in defs:
        tag = FactorTag(name=name, category=category, description=desc)
        db.session.add(tag)
        tags[name] = tag
    db.session.flush()
    return tags


def _seed_varieties():
    defs = [
        dict(
            code="SA", name="纯碱", exchange="郑商所", sector="能源化工",
            unit="20吨/手", tick_size=1.0, contract_months="1,5,9",
            pricing_type="国内供需型", anchor_benchmark="国内纯碱行业开工率/库存",
            linkage_coefficient=0.2,
            cost_note="氨碱法约1500元/吨，联碱法约1300元/吨，天然碱法约880元/吨——不同工艺成本差异巨大，"
                      "天然碱法产能扩张是压低行业成本中枢的核心变量",
            import_cost_note="纯碱基本自给，进口占比很低，此字段主要做占位",
            profit_status="亏损", historical_low=1150, historical_high=3550,
            intro="纯碱是典型的国内供需主导品种，核心矛盾是产能扩张(天然碱法)与需求(浮法玻璃/光伏玻璃)增速的错配。",
            storability="耐储存",
            storability_note="纯碱是无机盐，常温常压下化学性质稳定，不易变质，仓储成本低、没有保质期硬约束，"
                              "历史上行业库存能够堆积到很高水平并持续压制价格很长时间——'库存高'对纯碱往往"
                              "意味着压力会持续释放很久，而不是很快被动消化掉。",
        ),
        dict(
            code="FG", name="玻璃", exchange="郑商所", sector="能源化工",
            unit="20吨/手", tick_size=1.0, contract_months="1,5,9",
            pricing_type="国内供需型", anchor_benchmark="地产竣工数据、纯碱成本",
            linkage_coefficient=0.15,
            cost_note="浮法玻璃现金成本随纯碱、天然气/石油焦价格波动，行业普遍在盈亏平衡附近震荡",
            import_cost_note="基本无进口依赖",
            profit_status="亏损", historical_low=900, historical_high=2600,
            intro="玻璃需求与地产竣工强相关，是判断该品种最重要的单一变量，同时成本端受纯碱价格牵动。",
            storability="耐储存",
            storability_note="玻璃本身不会变质，储存周期理论上很长，但体积大、易碎、仓储/搬运成本比纯碱更高，"
                              "现实中厂库和社会库存不会无限堆积——库存压力更多体现为'厂家被迫降价走量'，"
                              "而不是像纯碱那样能长期'囤着等价格'。",
        ),
        dict(
            code="M", name="豆粕", exchange="大商所", sector="农产品",
            unit="10吨/手", tick_size=1.0, contract_months="1,3,5,7,8,9,11,12",
            pricing_type="进口依赖型", anchor_benchmark="CBOT美豆",
            linkage_coefficient=0.75,
            cost_note="国内压榨成本主要由进口大豆到岸成本决定",
            import_cost_note="进口大豆到岸成本 = CBOT美豆价格 x 汇率 + 海运费 + 关税及杂费，是核心定价锚",
            profit_status="盈亏平衡", historical_low=2450, historical_high=4200,
            intro="豆粕是典型的进口依赖型品种，价格主要跟随CBOT美豆和人民币汇率联动，国内基本面更多影响基差。",
            storability="不耐储存",
            storability_note="豆粕是蛋白粉，容易受潮结块、氧化变质，长期存放会影响蛋白质活性和适口性，"
                              "饲料厂普遍随用随采、很少建立大量安全库存——同样是'库存偏高'，对豆粕往往只是"
                              "短期错配，很快会被消化掉，持续性通常明显弱于纯碱、玻璃这类耐储存的工业品。",
        ),
    ]
    varieties = {}
    for d in defs:
        v = Variety(**d)
        db.session.add(v)
        varieties[d["code"]] = v
    db.session.flush()

    for code, v in varieties.items():
        db.session.add(Contract(variety_id=v.id, contract_code=f"{code}.main", is_main=True))
    db.session.flush()
    return varieties


def _seed_variety_factors(varieties, tags):
    plan = {
        "SA": [
            ("产能治理落地", 5, "重点跟踪工信部/发改委产能治理相关文件是否正式发布"),
            ("政策喊话反内卷", 4, "跟踪中央经济工作会议、行业协会会议提法"),
            ("产能检修", 3, "跟踪主要厂家检修计划和意外停车"),
            ("下游开工", 3, "跟踪浮法玻璃、光伏玻璃开工率"),
            ("供需突变", 4, "跟踪行业库存周度数据"),
        ],
        "FG": [
            ("地产需求", 5, "跟踪地产竣工面积同比数据，这是核心变量"),
            ("产能检修", 3, "跟踪冷修/复产窑炉数量变化"),
            ("政策喊话反内卷", 3, "跟踪产能置换、能耗双控相关政策"),
            ("供需突变", 3, "跟踪厂库+社会库存周度变化"),
        ],
        "M": [
            ("天气异常", 5, "跟踪美豆主产区生长季天气(种植/开花/结荚期)"),
            ("汇率波动", 4, "跟踪人民币兑美元汇率走势"),
            ("进口收紧", 3, "跟踪中美贸易政策、关税变化"),
            ("出口需求", 2, "跟踪国内养殖需求及生猪存栏变化"),
            ("供需突变", 3, "跟踪USDA月度供需报告"),
        ],
    }
    for code, items in plan.items():
        v = varieties[code]
        for tag_name, rank, note in items:
            db.session.add(
                VarietyFactor(
                    variety_id=v.id, factor_tag_id=tags[tag_name].id,
                    importance_rank=rank, monitoring_note=note, current_status="平静",
                )
            )
    db.session.flush()


def _seed_production_and_supply_chain(varieties):
    """
    生产端工艺/来源路线 + 上下游产业链成本占比。这里落地的是"某品种有几条并行的生产
    路径、各自成本和占比多少、有没有副产品能反过来补贴主产品成本"这几个此前完全没有
    覆盖的问题——尤其是副产品盈利这一条，直接决定了"价格跌破现金成本就一定要减产"
    这个朴素判断在哪些品种上会失灵、失灵到什么程度。
    """
    routes = {
        "SA": [
            dict(route_name="联碱法", route_type="工艺", market_share_pct=45, cash_cost=1300,
                 produces_only_this=False, byproduct_name="氯化铵",
                 byproduct_profit_note="氯化铵是复合肥的原料，需求相对独立于纯碱。只要氯化铵还能卖出合理价格，"
                                        "联碱法工厂即使纯碱现金流转负，也有动力继续开工消化联产的氯化铵——"
                                        "这意味着单看纯碱现金成本去判断'跌到这个价该减产了'，对联碱法产能会"
                                        "系统性地判断偏早，实际减产往往来得比纯成本测算更晚。",
                 note="国内最主流的工艺路线，占比最高"),
            dict(route_name="氨碱法", route_type="工艺", market_share_pct=30, cash_cost=1500,
                 produces_only_this=True, byproduct_name=None,
                 byproduct_profit_note=None,
                 note="又称索尔维法，副产的氯化钙经济价值很低，基本不构成成本支撑，"
                      "价格跌破现金成本后减产反应是三条工艺路线里最直接的"),
            dict(route_name="天然碱法", route_type="工艺", market_share_pct=25, cash_cost=880,
                 produces_only_this=True, byproduct_name=None,
                 byproduct_profit_note=None,
                 note="直接开采天然碱矿加工，省去了合成步骤，成本结构性地远低于另外两条工艺路线，"
                      "是压低全行业成本中枢、驱动产能扩张的核心变量"),
        ],
        "FG": [
            dict(route_name="浮法工艺(煤制气)", route_type="工艺", market_share_pct=55, cash_cost=1180,
                 produces_only_this=True, byproduct_name=None, byproduct_profit_note=None,
                 note="以煤制气为燃料，成本受煤炭价格牵动，是目前占比最高的燃料路线"),
            dict(route_name="浮法工艺(天然气)", route_type="工艺", market_share_pct=30, cash_cost=1260,
                 produces_only_this=True, byproduct_name=None, byproduct_profit_note=None,
                 note="以天然气为燃料，成本受天然气价格季节性波动影响更大，冬季采暖季成本压力通常上升"),
            dict(route_name="浮法工艺(石油焦)", route_type="工艺", market_share_pct=15, cash_cost=1140,
                 produces_only_this=True, byproduct_name=None, byproduct_profit_note=None,
                 note="以石油焦为燃料，成本最低但环保压力也最大，是产能治理政策重点针对的路线"),
        ],
        "M": [
            dict(route_name="巴西大豆压榨", route_type="原料产地", market_share_pct=60, cash_cost=3050,
                 produces_only_this=False, byproduct_name="豆油",
                 byproduct_profit_note="大豆压榨天然是'一压两得'——压榨大豆同时产出豆粕和豆油，这是理解豆粕成本"
                                        "支撑最容易被忽略的一点：压榨厂真正关心的是'压榨利润'(豆粕收入+豆油收入-"
                                        "大豆成本)，不是豆粕单独盈亏。豆油价格走强时，即使豆粕现货亏钱，压榨厂"
                                        "也愿意维持较高开机率去多产豆油，这会让豆粕供应比'单看豆粕自身成本'时"
                                        "更充裕、价格更抗跌不起来——分析豆粕成本必须同时看豆油这条腿。",
                 note="巴西是目前最大的大豆进口来源，到岸成本相对更低"),
            dict(route_name="美国大豆压榨", route_type="原料产地", market_share_pct=25, cash_cost=3180,
                 produces_only_this=False, byproduct_name="豆油",
                 byproduct_profit_note="同样遵循压榨利润逻辑，但到岸成本受关税政策和北美出口节奏影响更大，"
                                        "中美贸易关系变化时这条路线的成本波动通常比巴西路线更剧烈。",
                 note="采购窗口集中在美豆收割后的四季度到次年一季度"),
            dict(route_name="阿根廷大豆压榨", route_type="原料产地", market_share_pct=15, cash_cost=3020,
                 produces_only_this=False, byproduct_name="豆油",
                 byproduct_profit_note="阿根廷出口关税政策调整频繁，一旦下调出口税会短期内明显压低这条路线的"
                                        "到岸成本，同样通过'压榨利润'这条逻辑传导到豆粕供应意愿上。",
                 note="出口政策变化是这条路线成本波动的主要来源"),
        ],
    }
    for code, defs in routes.items():
        v = varieties[code]
        for d in defs:
            db.session.add(ProductionRoute(variety_id=v.id, **d))

    chains = {
        "SA": {
            "upstream": [
                ("原盐", 20, "氨碱法/联碱法的主要原料之一，价格波动相对温和"),
                ("石灰石", 8, "氨碱法/联碱法辅料，占成本比例不高"),
                ("天然碱矿", 100, "天然碱法直接开采矿石加工，不需要额外的化学合成原料，"
                                  "这也是它成本结构性更低的原因"),
            ],
            "downstream": [
                ("浮法玻璃", 15, "纯碱是浮法玻璃仅次于燃料的第二大成本项，玻璃开工率变化会直接传导到纯碱需求"),
                ("光伏玻璃", 12, "光伏玻璃扩产曾是纯碱需求最大的边际增量来源，但近两年增速明显放缓"),
                ("日用玻璃/洗涤剂等", 5, "占比相对分散的需求项，波动通常不构成主要矛盾"),
            ],
        },
        "FG": {
            "upstream": [
                ("纯碱", 35, "浮法玻璃仅次于燃料的第二大成本项，纯碱价格上涨会直接压缩玻璃利润"),
                ("燃料(煤制气/天然气/石油焦)", 40, "占比最高的成本项，具体品种取决于工艺路线"),
                ("石英砂", 8, "占比不高，价格相对稳定"),
            ],
            "downstream": [
                ("地产竣工(建筑玻璃)", 65, "玻璃需求最大的单一下游，地产竣工数据是判断玻璃需求最重要的变量"),
                ("汽车玻璃", 15, "需求相对独立于地产周期，波动更平稳"),
                ("光伏压延玻璃", 12, "光伏装机增速驱动的差异化需求，跟建筑玻璃周期不完全同步"),
            ],
        },
        "M": {
            "upstream": [
                ("进口大豆到岸成本", 85, "国内压榨成本里占绝对大头的一项，等于CBOT美豆价格x汇率+海运费+关税"),
                ("压榨加工费", 10, "包含能耗、人工等固定加工成本，波动远小于大豆本身"),
            ],
            "downstream": [
                ("生猪养殖", 55, "豆粕最大的下游需求，生猪存栏和养殖利润直接决定豆粕采购意愿"),
                ("水产养殖", 20, "季节性较强，通常在投苗旺季集中采购"),
                ("禽类饲料", 18, "需求相对平稳，波动性弱于生猪和水产"),
            ],
        },
    }
    for code, sides in chains.items():
        v = varieties[code]
        for direction, items in sides.items():
            for i, (name, pct, note) in enumerate(items, start=1):
                db.session.add(SupplyChainNode(
                    variety_id=v.id, direction=direction, order_index=i,
                    name=name, cost_share_pct=pct, note=note,
                ))
    db.session.flush()


def _sa_case_defs():
    return [
        dict(
            name="2025年纯碱反内卷预期行情", event_type="政策喊话反内卷",
            start_date=date(2025, 6, 10), extreme_date=date(2025, 7, 5), end_date=date(2025, 9, 15),
            price_start=1420, price_extreme=1980, price_end=1480,
            event_description="2025年6月中旬起，行业协会及部分媒体多次提及\"纯碱行业反内卷、有序化解过剩产能\"，"
                               "但截至三季度末未见正式产能退出文件。",
            market_interpretation_then="市场解读为政策将强制推动产能出清，供给收缩预期强烈，资金快速追多。",
            real_driver_after_review="复盘看真正驱动更多是资金对政策预期的短期博弈，现货端持续累库、行业仍在亏损，"
                                      "并没有实质产能退出，属于典型的预期先行、现实证伪。",
            inventory_level_then="高位", demand_status_then="疲弱", profit_status_then="亏损",
            final_price_landing="情绪消退后价格基本回落至喊话前的水平附近，未能维持在高位",
            policy_materialized="未落地", is_failure_case=True,
            pricing_regime_then="国内供需型",
            trigger_origin="催生型", precipitating_mechanism="容忍阈值型",
            setup_start_date=date(2025, 2, 1),
            setup_description="早在2025年2月，行业就已经连续5个月全面亏损，库存维持在历史高位附近，"
                               "市场从那时起就在讨论\"亏成这样迟早要有政策\"——6月的喊话只是这种长期痛苦的"
                               "一次滞后确认，不是凭空出现的冲击。",
            pre_event_chip_anomaly="喊话被媒体广泛报道前约两周，主力合约持仓量已经出现异常增加，"
                                    "同期仓单悄然小幅下降，不排除部分资金提前嗅到风声布局。",
            lessons="政策喊话阶段的脉冲行情持续时间通常不超过1-2个月，不宜追高；\n"
                    "没有具体产能退出文件之前，不该把喊话当成趋势反转信号；\n"
                    "高库存+全行业亏损状态下的反弹，更容易是资金驱动的反抽而非真正反转。",
            timeline=[
                (date(2025, 6, 10), 1420, "预期炒作期", "行业会议提及反内卷，盘面开始试探性拉升"),
                (date(2025, 6, 25), 1720, "预期炒作期", "多头资金加速进场，持仓量快速攀升"),
                (date(2025, 7, 5), 1980, "情绪消退期", "价格触及阶段高点，随后现货报价未跟涨，基差走弱"),
                (date(2025, 7, 25), 1690, "情绪消退期", "现货成交清淡，持仓量开始连续下降"),
                (date(2025, 9, 15), 1480, "现实回归期", "库存数据仍在累积，价格基本回吐全部涨幅"),
            ],
        ),
        dict(
            name="2024年纯碱累库下跌行情", event_type="供需突变",
            start_date=date(2024, 3, 1), extreme_date=date(2024, 6, 10), end_date=date(2024, 8, 20),
            price_start=2050, price_extreme=1580, price_end=1600,
            event_description="2024年上半年天然碱法新增产能持续释放，行业库存从中位快速攀升至历史高位。",
            market_interpretation_then="市场普遍认为新增产能会持续压制价格，下跌逻辑清晰。",
            real_driver_after_review="复盘看市场解读和真实驱动基本一致，是少数\"逻辑兑现\"的案例，"
                                      "价格随库存累积同步下移，没有明显的预期差。",
            inventory_level_then="低位", demand_status_then="正常", profit_status_then="盈亏平衡",
            final_price_landing="价格在新增产能持续释放下维持低位震荡，未见明显反弹",
            policy_materialized="落地", is_failure_case=False,
            pricing_regime_then="国内供需型",
            trigger_origin="外生冲击型", precipitating_mechanism=None,
            setup_start_date=None, setup_description=None, pre_event_chip_anomaly=None,
            lessons="供给端确定性强的新增产能释放行情，趋势可持续时间比事件驱动行情长得多；\n"
                    "库存趋势比单日价格波动更能说明问题，应作为核心跟踪指标。",
            timeline=[
                (date(2024, 3, 1), 2050, "现实回归期", "新增产能陆续投产，周度库存开始超预期累积"),
                (date(2024, 6, 10), 1580, "现实回归期", "库存达到历史高位，价格跌至三年低位"),
                (date(2024, 8, 20), 1600, "现实回归期", "供需矛盾未缓解，价格维持底部震荡"),
            ],
        ),
    ]


def _fg_case_defs():
    return [
        dict(
            name="2025年玻璃反内卷+地产预期共振行情", event_type="政策喊话反内卷",
            start_date=date(2025, 6, 20), extreme_date=date(2025, 7, 15), end_date=date(2025, 9, 20),
            price_start=1080, price_extreme=1420, price_end=1140,
            event_description="与纯碱同期，玻璃也受益于\"反内卷\"提法叠加对下半年地产竣工回暖的预期。",
            market_interpretation_then="市场预期产能治理+地产竣工回暖会带来供需双重改善。",
            real_driver_after_review="复盘看地产竣工数据并未明显改善，反弹更多是低位库存去化后的补库行情，"
                                      "叠加纯碱同期上涨带来的成本支撑联动。",
            inventory_level_then="高位", demand_status_then="疲弱", profit_status_then="亏损",
            final_price_landing="价格随纯碱回落同步走弱，未能维持独立上涨",
            policy_materialized="部分落地", is_failure_case=True,
            pricing_regime_then="国内供需型",
            trigger_origin="催生型", precipitating_mechanism="容忍阈值型",
            setup_start_date=date(2025, 2, 1),
            setup_description="与纯碱同期，玻璃行业也已经连续多个季度全面亏损，这轮\"反内卷\"叙事从一开始"
                               "就是纯碱和玻璃两个品种共振传播的，事前的行业痛苦程度是共同的背景。",
            pre_event_chip_anomaly=None,
            lessons="同一轮宏观叙事(反内卷)会同时驱动多个相关品种，容易形成板块共振，但也意味着一旦证伪是同步回落；\n"
                    "地产竣工预期类的行情，一定要等实际数据确认，不能只靠预期交易。",
            timeline=[
                (date(2025, 6, 20), 1080, "预期炒作期", "跟随纯碱反内卷情绪同步走强"),
                (date(2025, 7, 15), 1420, "情绪消退期", "价格触及高点，现货成交未见明显放量"),
                (date(2025, 9, 20), 1140, "现实回归期", "地产数据持续偏弱，价格跟随纯碱回落"),
            ],
        ),
        dict(
            name="2024年现货去库支撑反弹案例", event_type="下游开工",
            start_date=date(2024, 3, 1), extreme_date=date(2024, 5, 10), end_date=date(2024, 6, 30),
            price_start=1350, price_extreme=1780, price_end=1620,
            event_description="春季旺季下游深加工订单季节性回升，厂库去化速度明显加快。",
            market_interpretation_then="市场认为季节性旺季叠加低库存会带来一轮持续上涨。",
            real_driver_after_review="真实驱动比市场当时的解读更深一层：低库存本身已经持续了近4个月，"
                                      "价格早就跌到了历史低位区间难以再跌，旺季订单只是压垮骆驼的最后一根稻草，"
                                      "即便订单力度一般，极端低位的价格本身也已经具备自我修复的条件。",
            inventory_level_then="低位", demand_status_then="旺盛", profit_status_then="盈亏平衡",
            final_price_landing="旺季结束后价格从高点回落，但未跌破启动前水平",
            policy_materialized="不适用", is_failure_case=False,
            pricing_regime_then="国内供需型",
            trigger_origin="催生型", precipitating_mechanism="物极必反型",
            setup_start_date=date(2023, 11, 1),
            setup_description="价格从2023年11月起就已经在历史低位区间(约10-15%分位)反复磨底，"
                               "持续了近4个月，厂库也维持历史低位，属于典型的\"跌不动了\"状态——"
                               "旺季需求只是给了这次自我修复一个借口，不是根本原因。",
            pre_event_chip_anomaly=None,
            lessons="季节性行情逻辑相对可靠，但要提前预判旺季结束的时间窗口，不要恋战；\n"
                    "价格已经在历史低位磨了很久之后的反弹，即便触发的由头看起来一般，也不要轻视其反弹力度。",
            timeline=[
                (date(2024, 3, 1), 1350, "预期炒作期", "春季旺季订单回升，厂库去化"),
                (date(2024, 5, 10), 1780, "情绪消退期", "价格达到高点，旺季接近尾声"),
                (date(2024, 6, 30), 1620, "现实回归期", "需求季节性回落，价格从高点小幅修正"),
            ],
        ),
    ]


def _m_case_defs():
    return [
        dict(
            name="2024年美豆丰产预期下跌行情", event_type="供需突变",
            start_date=date(2024, 7, 1), extreme_date=date(2024, 9, 20), end_date=date(2024, 11, 30),
            price_start=3400, price_extreme=2900, price_end=2950,
            event_description="2024年美豆主产区天气良好，USDA多次上调单产预估，市场提前交易丰产预期。",
            market_interpretation_then="市场认为丰产会大幅增加供应，价格应当持续走弱。",
            real_driver_after_review="复盘看市场解读与真实驱动基本一致，属于\"一致预期顺利兑现\"的案例，"
                                      "但下跌后期跌幅略超基本面本身可以解释的幅度，存在一定资金层面的顺势加码。",
            inventory_level_then="中位", demand_status_then="正常", profit_status_then="盈亏平衡",
            final_price_landing="价格在丰产确认后维持低位，未见明显反弹",
            policy_materialized="不适用", is_failure_case=False,
            pricing_regime_then="进口依赖型",
            trigger_origin="外生冲击型", precipitating_mechanism=None,
            setup_start_date=None, setup_description=None, pre_event_chip_anomaly=None,
            lessons="天气驱动的供给预期行情，USDA月度报告是最重要的验证节点，报告日前后波动往往最大；\n"
                    "一致预期的行情即使方向正确，也要留意资金顺势加码带来的超调风险。",
            timeline=[
                (date(2024, 7, 1), 3400, "预期炒作期", "市场开始交易美豆丰产预期"),
                (date(2024, 9, 20), 2900, "现实回归期", "USDA报告确认高单产，价格加速下跌"),
                (date(2024, 11, 30), 2950, "现实回归期", "丰产基本兑现完毕，价格低位企稳"),
            ],
        ),
        dict(
            name="2025年汇率波动引发的进口成本重估行情", event_type="汇率波动",
            start_date=date(2025, 11, 1), extreme_date=date(2025, 12, 10), end_date=date(2026, 1, 20),
            price_start=3050, price_extreme=3380, price_end=3180,
            event_description="人民币兑美元汇率在2025年11-12月出现较大幅度波动，带动进口大豆到岸成本重估。",
            market_interpretation_then="市场解读为汇率贬值直接推高进口成本，应等比例推升豆粕价格。",
            real_driver_after_review="真实驱动比市场最初解读的更复杂：汇率只是触发因素，真正走出行情靠的是"
                                      "同期南美天气也出现扰动，两个因素叠加放大了涨幅，单独的汇率变化本身涨幅有限。",
            inventory_level_then="中位", demand_status_then="正常", profit_status_then="盈亏平衡",
            final_price_landing="随南美天气扰动缓解，价格从高点温和回落但未回到起点",
            policy_materialized="不适用", is_failure_case=False,
            pricing_regime_then="进口依赖型",
            trigger_origin="外生冲击型", precipitating_mechanism=None,
            setup_start_date=None, setup_description=None, pre_event_chip_anomaly=None,
            lessons="进口依赖型品种的行情很少是单一因素驱动，汇率+海外天气+海外供需经常同时起作用，"
                    "只盯一个因素容易低估或高估波动幅度。",
            timeline=[
                (date(2025, 11, 1), 3050, "预期炒作期", "人民币汇率大幅波动，成本重估预期发酵"),
                (date(2025, 12, 10), 3380, "情绪消退期", "南美天气扰动叠加，涨幅超出单一汇率因素能解释的范围"),
                (date(2026, 1, 20), 3180, "现实回归期", "南美天气扰动缓解，价格温和回落"),
            ],
        ),
    ]


def _seed_market_data(variety, dates, base_price, daily_vol, seed, case_windows, oi_base, wh_base):
    contract = Contract.query.filter_by(variety_id=variety.id, is_main=True).first()

    windows = [
        dict(start_date=c["start_date"], end_date=c["end_date"], price_start=c["price_start"],
             price_extreme=c["price_extreme"], price_end=c["price_end"])
        for c in case_windows
    ]
    prices = build_price_path(dates, base_price, daily_vol, seed, windows)

    rng = random.Random(seed + 1)
    oi_level = float(oi_base)  # 均值回归的"基础持仓水平"，跟下面的临时脉冲分开，脉冲结束后会自然回落
    for i, d in enumerate(dates):
        close = round(prices[i], 1)
        daily_range = abs(rng.gauss(0, daily_vol * 0.8)) + daily_vol * 0.3
        o = round(close + rng.gauss(0, daily_vol * 0.3), 1)
        h = round(max(o, close) + daily_range * 0.5, 1)
        l = round(min(o, close) - daily_range * 0.5, 1)
        vol = int(max(5000, rng.gauss(80000, 20000) + abs(close - (prices[i - 1] if i else close)) * 500))

        # 持仓量：基础水平围绕oi_base均值回归，案例窗口内叠加一个当天就会算完、
        # 不会累积进基础水平的高斯脉冲——脉冲峰值在窗口29%进度处，前后自然回落，
        # 这样窗口结束后持仓量会回到正常水平，而不是永久性地越垒越高（早期版本的bug）。
        oi_level += (oi_base - oi_level) * 0.03 + rng.gauss(0, oi_base * 0.008)
        oi_level = max(oi_base * 0.5, oi_level)
        bump = 0
        for w in windows:
            if w["start_date"] <= d <= w["end_date"]:
                span = max(1, (w["end_date"] - w["start_date"]).days)
                progress = (d - w["start_date"]).days / span
                bump += oi_base * 0.35 * math.exp(-((progress - 0.3) ** 2) / (2 * 0.12 ** 2))
        oi = int(max(oi_base * 0.4, oi_level + bump))

        db.session.add(DailyBar(
            contract_id=contract.id, trade_date=d, open=o, high=h, low=l, close=close,
            settle=close, volume=vol, open_interest=oi,
        ))

        top5_long = round(min(65, max(15, 28 + rng.gauss(0, 6))), 1)
        top5_short = round(min(65, max(15, 30 + rng.gauss(0, 6))), 1)
        db.session.add(PositionRank(
            contract_id=contract.id, trade_date=d, total_open_interest=oi,
            top5_long_ratio=top5_long, top5_short_ratio=top5_short,
        ))

        wh = int(max(wh_base * 0.3, rng.gauss(wh_base, wh_base * 0.15)))
        # 案例窗口后期，仓单往往骤减（交割逻辑/去库），制造一个"仓单异常"的示例信号
        for w in windows:
            if w["end_date"] <= d <= w["end_date"] + timedelta(days=10):
                wh = int(wh * 0.6)
        db.session.add(WarehouseReceipt(contract_id=contract.id, trade_date=d, receipt_qty=wh))

        spot = round(close * (1 + rng.gauss(0, 0.01)), 1)
        db.session.add(Basis(
            contract_id=contract.id, trade_date=d, futures_price=close, spot_price=spot,
            basis_value=round(spot - close, 1),
        ))

        if i % 200 == 0:
            db.session.flush()

    db.session.flush()


def _seed_cases(variety, case_defs, tags):
    created = {}
    for c in case_defs:
        case = Case(
            variety_id=variety.id, name=c["name"], start_date=c["start_date"], end_date=c["end_date"],
            price_start=c["price_start"], price_extreme=c["price_extreme"], price_end=c["price_end"],
            event_type_id=tags[c["event_type"]].id, event_description=c["event_description"],
            market_interpretation_then=c["market_interpretation_then"],
            real_driver_after_review=c["real_driver_after_review"],
            inventory_level_then=c["inventory_level_then"], demand_status_then=c["demand_status_then"],
            profit_status_then=c["profit_status_then"], final_price_landing=c["final_price_landing"],
            policy_materialized=c["policy_materialized"], lessons=c["lessons"],
            is_failure_case=c["is_failure_case"], pricing_regime_then=c["pricing_regime_then"],
            trigger_origin=c.get("trigger_origin"), precipitating_mechanism=c.get("precipitating_mechanism"),
            setup_start_date=c.get("setup_start_date"), setup_description=c.get("setup_description"),
            pre_event_chip_anomaly=c.get("pre_event_chip_anomaly"),
        )
        db.session.add(case)
        db.session.flush()
        created[c["name"]] = case
        for ev_date, price, stage, desc in c["timeline"]:
            db.session.add(CaseTimeline(case_id=case.id, event_date=ev_date, price=price, stage=stage, description=desc))

        # 案例本身在K线图和日历上也应该能看到一个标注点。case_id 显式关联回这条案例，
        # 不再靠 source 字符串 + 日期去反推"这个标注属于哪个案例"。
        db.session.add(Event(
            variety_id=variety.id, event_date=c["start_date"], title=c["name"],
            description=c["event_description"], factor_tag_id=tags[c["event_type"]].id,
            level=2 if c["policy_materialized"] == "落地" else 1,
            source="历史案例库", case_id=case.id,
        ))
    db.session.flush()
    return created


def _seed_setup_episodes(variety, case_defs, created_cases):
    """
    给每个"催生型"案例补一条正例 SetupEpisode（链接回对应的Case），
    再刻意补1-2条反例——历史上也曾经到过差不多极端、但没有催生任何案例的情况，
    这样情景匹配算出来的转化率才是诚实的，而不是"极端了就一定会有事发生"的错觉。
    """
    for c in case_defs:
        if c.get("trigger_origin") != "催生型" or not c.get("setup_start_date"):
            continue
        case = created_cases[c["name"]]
        duration = (c["start_date"] - c["setup_start_date"]).days
        extreme_pct = 8 if c["inventory_level_then"] == "高位" and c["profit_status_then"] == "亏损" else 12
        db.session.add(SetupEpisode(
            variety_id=variety.id, dimension="价格", mechanism=c["precipitating_mechanism"],
            period_start=c["setup_start_date"], period_end=c["start_date"],
            extreme_percentile=extreme_pct, duration_days=duration,
            pre_event_signal=c["setup_description"],
            led_to_case_id=case.id,
            note=f"最终演变为案例《{case.name}》",
        ))
    db.session.flush()


def _seed_negative_setup_episodes(varieties):
    """反例库：这些极端状态最终什么都没催生，用来平衡正例、避免幸存者偏差。"""
    negatives = [
        dict(code="SA", mechanism="容忍阈值型", period_start=date(2023, 11, 1), period_end=date(2024, 2, 20),
             extreme_percentile=15, duration_days=(date(2024, 2, 20) - date(2023, 11, 1)).days,
             pre_event_signal="行业同样连续亏损近4个月、库存维持高位，市场也一度讨论政策会不会出手，"
                               "但始终没有出现明显的喊话或措施，价格延续弱势直到新增产能进一步压制。",
             note="没有催生任何政策响应或行情反转，痛苦程度和持续时间都不及2025年那一轮"),
        dict(code="FG", mechanism="容忍阈值型", period_start=date(2024, 9, 1), period_end=date(2024, 12, 15),
             extreme_percentile=18, duration_days=(date(2024, 12, 15) - date(2024, 9, 1)).days,
             pre_event_signal="行业亏损持续了约3个月，但比2025年那一轮浅、也短，市场当时几乎没有讨论反内卷政策。",
             note="价格自然震荡消化，未见明显反转或政策介入"),
        dict(code="M", mechanism="物极必反型", period_start=date(2024, 12, 1), period_end=date(2025, 2, 10),
             extreme_percentile=22, duration_days=(date(2025, 2, 10) - date(2024, 12, 1)).days,
             pre_event_signal="豆粕阶段性跌至历史20%分位附近，但当时国内需求正常、库存不高，"
                               "只是CBOT美豆阶段性走弱的跟随下跌。",
             note="价格随美豆企稳后自然修复，没有形成趋势性行情或特殊事件"),
    ]
    for n in negatives:
        db.session.add(SetupEpisode(
            variety_id=varieties[n["code"]].id, dimension="价格", mechanism=n["mechanism"],
            period_start=n["period_start"], period_end=n["period_end"],
            extreme_percentile=n["extreme_percentile"], duration_days=n["duration_days"],
            pre_event_signal=n["pre_event_signal"], led_to_case_id=None, note=n["note"],
        ))
    db.session.flush()


def _month_periods(start, end):
    periods = []
    d = date(start.year, start.month, 1)
    while d <= end:
        periods.append(d)
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return periods


def _seed_margin_series(varieties):
    """
    月度利润率序列，独立于价格生成。玻璃(FG)故意设计成最近几个月利润被强制拉到历史极低，
    但价格并不需要同步走到极端——这正是用来验证"利润维度能捕捉价格维度会漏掉的极端"。
    数值本身是任意单位(正=盈利、负=亏损)，只用来做百分位排名，不做跨品种绝对值比较。
    """
    periods = _month_periods(START_DATE, END_DATE)
    # 均值回归系数调高、波动调低，让"正常时期"的利润率老老实实待在base附近，
    # 这样后面强制拉出来的极端下跌才是一个真正意义上的历史级别异常，而不是被自然波动淹没。
    configs = {
        "SA": dict(base=-3, vol=2.5, seed=11, recent_dip=False),
        "FG": dict(base=2, vol=2.5, seed=22, recent_dip=True),
        "M": dict(base=4, vol=3, seed=33, recent_dip=False),
    }
    for code, cfg in configs.items():
        rng = random.Random(cfg["seed"])
        value = cfg["base"]
        values = []
        for _ in periods:
            value += (cfg["base"] - value) * 0.2 + rng.gauss(0, cfg["vol"])
            values.append(value)
        if cfg["recent_dip"]:
            dip_len = 5  # 最近5个月强制走出一段历史级别的利润挤压，且明显比历史自然波动更深
            span = max(1, dip_len - 1)
            floor = min(values) - 8  # 保证比历史最低点还低，确实是"历史级别"的极端，不是普通低谷
            for i in range(len(values) - dip_len, len(values)):
                t = (i - (len(values) - dip_len)) / span
                values[i] = floor - t * 3 + rng.gauss(0, 0.8)
        for p, v in zip(periods, values):
            db.session.add(ProfitMarginRecord(variety_id=varieties[code].id, period=p, margin_value=round(v, 2)))
    db.session.flush()


def _seed_margin_setup_episodes(varieties, fg_created):
    """给"利润"维度也补一组正反例，跟价格维度的 SetupEpisode 分开存放(dimension='利润')。"""
    fg_case = fg_created.get("2025年玻璃反内卷+地产预期共振行情")
    db.session.add(SetupEpisode(
        variety_id=varieties["FG"].id, dimension="利润", mechanism="容忍阈值型",
        period_start=date(2025, 1, 1), period_end=date(2025, 6, 20),
        extreme_percentile=6, duration_days=(date(2025, 6, 20) - date(2025, 1, 1)).days,
        pre_event_signal="利润率从2025年初就已经跌至历史极低水平，比价格本身走到极端更早发出信号——"
                          "这也是为什么只盯价格分位数会慢半拍。",
        led_to_case_id=fg_case.id if fg_case else None,
        note=f"最终演变为案例《{fg_case.name}》" if fg_case else None,
    ))
    db.session.add(SetupEpisode(
        variety_id=varieties["FG"].id, dimension="利润", mechanism="容忍阈值型",
        period_start=date(2024, 1, 1), period_end=date(2024, 5, 1),
        extreme_percentile=9, duration_days=(date(2024, 5, 1) - date(2024, 1, 1)).days,
        pre_event_signal="利润率也曾跌至历史低位附近，但恢复速度较快，没有演变成需要政策介入的持续性问题。",
        led_to_case_id=None,
        note="利润率在低位停留时间较短就自行修复，未催生任何案例",
    ))
    db.session.flush()


def _inject_recent_chip_anomaly(variety, days=15, drop_ratio=0.3):
    """
    在最近N个交易日，人为制造一次仓单骤减，用来演示"资金布局型"信号完全不依赖价格位置——
    即便豆粕价格当时并不处于历史极端分位，筹码异常通道也应该能独立检测到这个变化。
    """
    contract = Contract.query.filter_by(variety_id=variety.id, is_main=True).first()
    rows = (
        WarehouseReceipt.query.filter_by(contract_id=contract.id)
        .order_by(WarehouseReceipt.trade_date.desc())
        .limit(days)
        .all()
    )
    span = max(1, len(rows) - 1)
    for i, row in enumerate(rows):  # rows[0] 是最近一天，越靠近现在跌幅越大
        factor = drop_ratio + (1 - drop_ratio) * (i / span)
        row.receipt_qty = int(row.receipt_qty * factor)
    db.session.flush()


def _seed_recent_events(varieties, tags):
    """在数据末尾附近插入几条"最近事件"，让现状体检页面能演示出"偏热/异常"状态，而不是全部平静。"""
    recent = [
        ("SA", "产能检修", date(2026, 7, 20), "个别厂家检修传闻扰动市场情绪", 2),
        ("SA", "政策喊话反内卷", date(2026, 6, 25), "行业会议再提产能治理，尚无具体文件", 1),
        ("FG", "地产需求", date(2026, 7, 15), "地产竣工数据环比小幅回升", 2),
        ("M", "天气异常", date(2026, 7, 28), "美豆产区遭遇阶段性干旱预警", 1),
        ("M", "汇率波动", date(2026, 8, 5), "人民币兑美元汇率单日大幅波动", 2),
    ]
    for code, tag_name, d, title, level in recent:
        db.session.add(Event(
            variety_id=varieties[code].id, event_date=d, title=title,
            description=title, factor_tag_id=tags[tag_name].id, level=level, source="模拟最新资讯",
        ))
    db.session.flush()


def _seed_macro_and_policy():
    rng = random.Random(999)
    d = date(2023, 8, 1)
    pmi = 49.5
    cpi = 0.2
    usdcny = 7.15
    while d <= END_DATE:
        pmi = min(53, max(47, pmi + rng.gauss(0, 0.4)))
        cpi = min(2.5, max(-1.0, cpi + rng.gauss(0, 0.15)))
        usdcny = min(7.35, max(6.9, usdcny + rng.gauss(0, 0.03)))
        db.session.add(MacroData(indicator="PMI", report_date=d, value=round(pmi, 1)))
        db.session.add(MacroData(indicator="CPI同比", report_date=d, value=round(cpi, 1)))
        db.session.add(MacroData(indicator="USDCNY", report_date=d, value=round(usdcny, 2)))
        # 下个月1号
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)

    policies = [
        (date(2025, 6, 15), "多部委提及反内卷、有序化解重点行业过剩产能", "产业", 1,
         "中央层面多次表态治理低价无序竞争，尚处于表态阶段"),
        (date(2025, 12, 1), "重点行业产能治理实施方案陆续出台", "产业", 2,
         "部分省份出台具体产能置换/淘汰细则，进入措施落地阶段"),
        (date(2026, 3, 20), "全国两会重申稳增长、扩内需政策取向", "宏观", 1, "两会定调，具体细则待后续部委落地"),
    ]
    for d2, name, category, level, desc in policies:
        db.session.add(Policy(announced_date=d2, name=name, category=category, level=level, description=desc))
    db.session.flush()
