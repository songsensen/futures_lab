# -*- coding: utf-8 -*-
"""
数据模型说明
============
这里的表结构是把前面讨论的分析框架直接翻译成数据结构，核心是两条主线：

1. FactorTag（因素标签）是整个系统的"共用词汇表"——它同时挂在 VarietyFactor（品种该关注什么）
   和 Case / Event（历史上这个因素什么时候被触发过）上。没有这张表，"品种信息"和"历史案例"
   就是两个互不相关的库；有了它，两边才能互相指认、互相检索。

2. Case（历史案例）里特意把 market_interpretation_then（当时市场的主流解读）和
   real_driver_after_review（复盘后判断的真实驱动）拆成两个独立字段，而不是合并成一个
   "事件描述"——这两者不一致的案例，恰恰是最有参考价值的案例（讨论里提到的"幸存者偏差"
   和"叙事 vs 真实驱动"问题）。

- owner_id 字段先留空/不做约束，现在不做用户系统，以后要加鉴权时，直接给这些表的 owner_id
  接上真实用户表即可,不需要改表结构。
"""
from datetime import date

from app.extensions import db


# ---------------------------------------------------------------------------
# 一、品种基础信息模块
# ---------------------------------------------------------------------------

class Variety(db.Model):
    """品种基本信息 + 定价权归属 + 成本参考（对应需求文档模块一 1.1-1.3）"""

    __tablename__ = "variety"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False)  # 如 SA, FG, M
    name = db.Column(db.String(64), nullable=False)  # 纯碱、玻璃、豆粕
    exchange = db.Column(db.String(32))  # 郑商所/大商所/上期所/中金所/广期所
    sector = db.Column(db.String(32))  # 农产品/黑色系/有色金属/能源化工/贵金属
    unit = db.Column(db.String(32))  # 交易单位，如 20吨/手
    tick_size = db.Column(db.Float)  # 最小变动价位
    contract_months = db.Column(db.String(64))  # 如 "1,3,5,7,8,9,11"

    # 1.2 定价权归属
    pricing_type = db.Column(db.String(32))  # 进口依赖型 / 国内供需型 / 全球金融属性型
    anchor_benchmark = db.Column(db.String(128))  # 核心锚定标的，如 "CBOT美豆"
    linkage_coefficient = db.Column(db.Float)  # 内外盘联动系数（粗略估算）

    # 1.3 成本参考
    cost_note = db.Column(db.Text)  # 生产成本区间说明（自由文本，比如多种工艺对比）
    import_cost_note = db.Column(db.Text)  # 进口成本参考
    profit_status = db.Column(db.String(16))  # 当前盈利 / 盈亏平衡 / 亏损
    historical_low = db.Column(db.Float)
    historical_high = db.Column(db.Float)

    intro = db.Column(db.Text)  # 一段简单介绍，展示在详情页顶部

    # 库存耐储存性——同样是"现状体检"要考虑的背景变量：耐储存的品种(纯碱/玻璃这类工业品，
    # 不易变质、仓储成本低)历史上能把库存堆到很高水平，库存本身就能持续压制价格很长时间；
    # 不耐储存的品种(豆粕这类蛋白粉，容易受潮结块变质)下游随用随采，库存很难长期堆积，
    # 同样的"库存高企"信号对这两类品种的含义和持续性完全不同。
    storability = db.Column(db.String(16))  # 耐储存 / 不耐储存 / 中等
    storability_note = db.Column(db.Text)

    factors = db.relationship("VarietyFactor", backref="variety", cascade="all, delete-orphan")
    contracts = db.relationship("Contract", backref="variety", cascade="all, delete-orphan")
    cases = db.relationship("Case", backref="variety", cascade="all, delete-orphan")
    production_routes = db.relationship(
        "ProductionRoute", backref="variety", cascade="all, delete-orphan",
        order_by="ProductionRoute.market_share_pct.desc()",
    )
    supply_chain_nodes = db.relationship(
        "SupplyChainNode", backref="variety", cascade="all, delete-orphan",
        order_by="SupplyChainNode.order_index",
    )

    def __repr__(self):
        return f"<Variety {self.code} {self.name}>"

    def __str__(self):
        # /admin 后台的外键下拉框和列表默认用 str()，不用 repr() 那种带尖括号的调试格式
        return f"{self.code} {self.name}"


class ProductionRoute(db.Model):
    """
    生产端的工艺路线/原料来源（对应"某品种有哪几种生产工艺、当前占比、成本、
    是否有副产品"这几个问题）。工业品(比如纯碱)对应的是不同工艺技术路线；
    农产品加工品(比如豆粕)对应的是不同产地的原料来源(巴西大豆/美国大豆/阿根廷大豆)——
    两者本质都是"同一个最终品种，背后有几条并行、成本结构不同的生产路径"，所以
    用同一张表建模，不用为工业品和农产品分别建表。

    byproduct 相关字段是这里最重要的信息：如果一条工艺路线除了主产品还产出有价值的
    副产品(比如联碱法产氯化铵、大豆压榨产豆油)，那么只要副产品还盈利，工厂就有动力
    在主产品(纯碱/豆粕)现金流为负的情况下继续开工——这意味着"价格跌破现金成本"
    这个传统判断对这类工艺路线会失真，主产品低价能维持的时间比单纯看自身成本线
    要长得多，这正是分析这个品种时容易被忽略的一个关键变量。
    """

    __tablename__ = "production_route"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    route_name = db.Column(db.String(64), nullable=False)  # 如"联碱法""巴西大豆压榨"
    route_type = db.Column(db.String(16))  # 工艺 / 原料产地
    market_share_pct = db.Column(db.Float)  # 当前占该品种总供应的比例(%)
    cash_cost = db.Column(db.Float)  # 现金成本，单位和品种的价格单位一致，方便直接对比
    produces_only_this = db.Column(db.Boolean, default=True)  # 是否只产出该品种，没有可观的副产品
    byproduct_name = db.Column(db.String(64))  # 副产品名称，没有则为空
    byproduct_profit_note = db.Column(db.Text)  # 副产品当前盈利状况，以及这对主产品成本支撑的影响
    note = db.Column(db.Text)


class SupplyChainNode(db.Model):
    """
    上下游产业链节点，加上"成本/需求占比"——回答"这个品种的成本主要来自哪里、
    它自己又占下游产品成本的多少"这类问题。direction 区分是在品种的上游(原料端)
    还是下游(需求端)，order_index 控制展示顺序(数字越小离品种本身越近)。
    cost_share_pct 的含义会随方向变化：上游节点表示"这项原料成本占该品种生产成本的
    比例"；下游节点表示"该品种的成本占下游产品总成本的比例"——数字不是拿来跨节点
    累加的，只是各自局部的一个参考比例，避免暗示一种它们本来没有的精确可加性。
    """

    __tablename__ = "supply_chain_node"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    direction = db.Column(db.String(8), nullable=False)  # upstream / downstream
    order_index = db.Column(db.Integer, default=1)
    name = db.Column(db.String(64), nullable=False)
    cost_share_pct = db.Column(db.Float)  # 含义见上面类注释，可能为空(有些环节没有可靠的公开比例数据)
    note = db.Column(db.Text)


class FactorTag(db.Model):
    """
    共用标签体系——品种关注点清单和历史案例共用同一套标签，这是两个模块能互相
    指认、互相检索的关键接口。category 分供应端/需求端/宏观，方便按大类筛选。
    """

    __tablename__ = "factor_tag"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)  # 如"政策喊话""天气异常""逼仓"
    category = db.Column(db.String(16))  # 供应端 / 需求端 / 宏观
    description = db.Column(db.Text)

    def __repr__(self):
        return f"<FactorTag {self.name}>"

    def __str__(self):
        return self.name


class VarietyFactor(db.Model):
    """
    品种关注点清单（对应模块一 1.4）——品种与因素标签的关联，带重要性排序。
    current_status 是"现状体检"的落地字段：平静 / 偏热 / 异常，由分析引擎根据最近
    的 Event 记录和价格/持仓分位数动态计算后写回这里，页面直接读，不用现场计算。
    """

    __tablename__ = "variety_factor"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    factor_tag_id = db.Column(db.Integer, db.ForeignKey("factor_tag.id"), nullable=False)

    importance_rank = db.Column(db.Integer, default=3)  # 1-5，5最重要
    monitoring_note = db.Column(db.String(256))  # 具体该看什么指标/渠道，比如"USDA月度供需报告"
    current_status = db.Column(db.String(16), default="平静")  # 平静 / 偏热 / 异常
    status_updated_on = db.Column(db.Date)

    factor_tag = db.relationship("FactorTag")


# ---------------------------------------------------------------------------
# 二、行情与筹码数据（用来支撑"现状体检"）
# ---------------------------------------------------------------------------

class Contract(db.Model):
    """合约（当前先按主力连续合约简化处理，一个品种一条主力连续序列）"""

    __tablename__ = "contract"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    contract_code = db.Column(db.String(32), nullable=False)  # 如 SA main / SA2601
    is_main = db.Column(db.Boolean, default=True)

    daily_bars = db.relationship("DailyBar", backref="contract", cascade="all, delete-orphan")
    position_ranks = db.relationship("PositionRank", backref="contract", cascade="all, delete-orphan")
    warehouse_receipts = db.relationship("WarehouseReceipt", backref="contract", cascade="all, delete-orphan")
    basis_records = db.relationship("Basis", backref="contract", cascade="all, delete-orphan")

    def __str__(self):
        return self.contract_code


class DailyBar(db.Model):
    """日行情（先用测试数据模拟，后续接爬虫/数据商）"""

    __tablename__ = "daily_bar"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contract.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    open = db.Column(db.Float)
    high = db.Column(db.Float)
    low = db.Column(db.Float)
    close = db.Column(db.Float)
    settle = db.Column(db.Float)
    volume = db.Column(db.Integer)
    open_interest = db.Column(db.Integer)

    __table_args__ = (db.UniqueConstraint("contract_id", "trade_date", name="uq_bar_contract_date"),)


class PositionRank(db.Model):
    """持仓龙虎榜简化版：前5席位多空集中度 + 总持仓量"""

    __tablename__ = "position_rank"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contract.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    total_open_interest = db.Column(db.Integer)
    top5_long_ratio = db.Column(db.Float)  # 前5多头席位占比
    top5_short_ratio = db.Column(db.Float)  # 前5空头席位占比

    __table_args__ = (db.UniqueConstraint("contract_id", "trade_date", name="uq_pos_contract_date"),)


class WarehouseReceipt(db.Model):
    """仓单日报"""

    __tablename__ = "warehouse_receipt"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contract.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    receipt_qty = db.Column(db.Integer)  # 仓单数量（折算为"手"，方便和持仓量直接对比）

    __table_args__ = (db.UniqueConstraint("contract_id", "trade_date", name="uq_wh_contract_date"),)


class Basis(db.Model):
    """期货-现货基差"""

    __tablename__ = "basis"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contract.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    futures_price = db.Column(db.Float)
    spot_price = db.Column(db.Float)
    basis_value = db.Column(db.Float)  # 现货-期货，正为升水

    __table_args__ = (db.UniqueConstraint("contract_id", "trade_date", name="uq_basis_contract_date"),)


# ---------------------------------------------------------------------------
# 三、历史案例库模块
# ---------------------------------------------------------------------------

class Case(db.Model):
    """
    历史案例（对应模块二）。event_type_id 是这条案例的主驱动因素标签，用于和
    VarietyFactor / Event 做匹配。inventory_level_then / demand_status_then /
    profit_status_then 是当时基本面状态的分类字段，情景匹配算法会拿现状的同一套
    分类去对比这三个字段，而不是只看价格位置。
    """

    __tablename__ = "case"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)  # 如"2025年玻璃反内卷预期行情"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    price_start = db.Column(db.Float)
    price_extreme = db.Column(db.Float)  # 峰值或谷值
    price_end = db.Column(db.Float)

    event_type_id = db.Column(db.Integer, db.ForeignKey("factor_tag.id"))
    event_description = db.Column(db.Text)  # 事件描述（精确时间+精确措辞）

    # 关键方法论字段：两者故意拆开，不一致的案例最有参考价值
    market_interpretation_then = db.Column(db.Text)  # 市场当时的主流解读
    real_driver_after_review = db.Column(db.Text)  # 复盘后判断的真实驱动（可以和上面不同）

    inventory_level_then = db.Column(db.String(16))  # 高位 / 中位 / 低位
    demand_status_then = db.Column(db.String(16))  # 旺盛 / 正常 / 疲弱
    profit_status_then = db.Column(db.String(16))  # 盈利 / 盈亏平衡 / 亏损

    final_price_landing = db.Column(db.Text)  # 最终价格回到了哪里
    policy_materialized = db.Column(db.String(16))  # 政策/事件是否真正落地：落地/未落地/部分落地
    lessons = db.Column(db.Text)  # 规律提炼，不超过3条，用换行分隔

    is_failure_case = db.Column(db.Boolean, default=False)  # 标记"逻辑没兑现"的案例，避免案例库幸存者偏差
    pricing_regime_then = db.Column(db.String(32))  # 当时的定价权归属状态，防止用旧逻辑套现在

    # --- 事前状态 / 催生机制字段 ---
    # 很多"事件"不是随机外生冲击，而是价格/筹码/基本面走到极端后被动"挤"出来的结果——
    # 事件是果不是因。trigger_origin 先分两大类，"催生型"才有必要往前找事前状态规律，
    # "外生冲击型"（真正随机的天气、地缘等）本质不可预判，标记出来是为了提醒自己
    # 不要在这类案例上浪费精力找事前征兆。
    trigger_origin = db.Column(db.String(16))  # 催生型 / 外生冲击型
    # 催生型再细分三种机制，对应讨论过的三种"事前状态→事件"的关系：
    # 资金布局型：内幕/嗅觉资金在公开事件前已提前动作，留痕在筹码数据里
    # 物极必反型：价格/利润本身走到极端，不需要外部事件配合就会自我反转
    # 容忍阈值型：政策/行业干预是对已存在的极端痛苦的滞后确认，不是随机冲击
    precipitating_mechanism = db.Column(db.String(16))  # 资金布局型 / 物极必反型 / 容忍阈值型

    setup_start_date = db.Column(db.Date)  # 极端状态真正开始的时间点，通常远早于start_date(新闻/情绪爆发点)
    setup_description = db.Column(db.Text)  # 事发前置状态描述：价格/利润/库存已经处于什么状态、持续多久
    pre_event_chip_anomaly = db.Column(db.Text)  # 事件公开前，持仓/仓单/成交量是否已经出现异常（资金布局型信号）

    event_type = db.relationship("FactorTag")
    timeline = db.relationship(
        "CaseTimeline", backref="case", cascade="all, delete-orphan", order_by="CaseTimeline.event_date"
    )

    def __str__(self):
        return self.name


class CaseTimeline(db.Model):
    """案例的关键节点时间线（对应 2.4 行情演绎过程）"""

    __tablename__ = "case_timeline"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("case.id"), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    price = db.Column(db.Float)
    stage = db.Column(db.String(16))  # 预期炒作期 / 情绪消退期 / 现实回归期
    description = db.Column(db.Text)


class SetupEpisode(db.Model):
    """
    "事前状态"观察记录——不只记录"最终催生了事件"的极端状态(那样会有幸存者偏差，
    让人误以为极端就一定会反转/催生政策)，也刻意记录历史上曾经到过差不多极端、
    但什么都没发生的情况。两种都放进同一张表，才能算出一个诚实的"这种状态历史上
    有多大概率会催生事件"的基础比率，而不是给人一种必然性的错觉。

    led_to_case_id 为空 = 这次极端状态最终没有催生任何案例(反例)；
    有值 = 这次极端状态后来确实演变成了对应的 Case(正例)。
    """

    __tablename__ = "setup_episode"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    dimension = db.Column(db.String(8), default="价格")  # 价格 / 利润 —— 极端是在哪个维度上观察到的
    mechanism = db.Column(db.String(16))  # 资金布局型 / 物极必反型 / 容忍阈值型
    period_start = db.Column(db.Date, nullable=False)  # 极端状态开始的时间
    period_end = db.Column(db.Date)  # 极端状态解除/被事件打断的时间
    extreme_percentile = db.Column(db.Integer)  # 当时所处历史百分位(价格或利润，取决于dimension)
    duration_days = db.Column(db.Integer)  # 处于极端状态的持续天数，情景匹配主要按这个分桶比较
    pre_event_signal = db.Column(db.Text)  # 观察到的具体信号：亏损持续时间、筹码异常等
    led_to_case_id = db.Column(db.Integer, db.ForeignKey("case.id"), nullable=True)
    note = db.Column(db.Text)  # 如果没有催生事件，说明后来实际怎么样了(不能留白，否则等于没有反例)

    variety = db.relationship("Variety")
    led_to_case = db.relationship("Case")


class ProfitMarginRecord(db.Model):
    """
    利润/成本状态时间序列（按月）——现状体检原来只用价格分位数判断"是否极端"，但价格没有
    历史极端时，利润率也可能因为成本端变化独立地陷入历史极值（比如原料涨价、价格没怎么跌，
    利润却已经历史最差）。这条序列让"物极必反/容忍阈值"这两种催生机制的判断，能同时看价格
    和利润两个维度，而不是只拿价格分位数硬凑代理——这是当前时间点判断"事前状态"时经常被
    忽略的一个独立信号来源，不依赖价格是否处于极端。
    """

    __tablename__ = "profit_margin_record"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=False)
    period = db.Column(db.Date, nullable=False)  # 用当月1号代表这个月
    margin_value = db.Column(db.Float)  # 简化的利润率数值，越低代表越亏

    __table_args__ = (db.UniqueConstraint("variety_id", "period", name="uq_margin_variety_period"),)


# ---------------------------------------------------------------------------
# 四、事件与日历模块（用于K线标注 + 日历时间线）
# ---------------------------------------------------------------------------

class Event(db.Model):
    """
    独立的事件记录，用于两个地方：K线图上按日期打标注点、日历时间线列表。
    factor_tag_id 关联共用标签体系，level 对应"政策信号分级"（模块六 6.3）。
    variety_id 可为空——宏观/全市场事件不特定于某个品种。
    """

    __tablename__ = "event"

    id = db.Column(db.Integer, primary_key=True)
    variety_id = db.Column(db.Integer, db.ForeignKey("variety.id"), nullable=True)
    event_date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    factor_tag_id = db.Column(db.Integer, db.ForeignKey("factor_tag.id"))
    level = db.Column(db.Integer, default=1)  # 1=喊话/预期 2=具体措施 3=基本面确认
    source = db.Column(db.String(128))
    # 之前"这条事件是不是案例库的锚点"完全靠 source 字符串 + 日期反推，凑巧对得上而已，
    # 后面接真实数据源很容易悄悄错位。显式外键把这层关系钉死，不再靠字符串猜。
    case_id = db.Column(db.Integer, db.ForeignKey("case.id"), nullable=True)

    variety = db.relationship("Variety")
    factor_tag = db.relationship("FactorTag")
    case = db.relationship("Case")


# ---------------------------------------------------------------------------
# 五、宏观与政策监控模块
# ---------------------------------------------------------------------------

class MacroData(db.Model):
    """宏观数据点，先做最简版本：日期+指标名+数值"""

    __tablename__ = "macro_data"

    id = db.Column(db.Integer, primary_key=True)
    indicator = db.Column(db.String(32), nullable=False)  # CPI/PPI/PMI/M2/美元指数...
    report_date = db.Column(db.Date, nullable=False)
    value = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint("indicator", "report_date", name="uq_macro_indicator_date"),)


class Policy(db.Model):
    """政策监控清单"""

    __tablename__ = "policy"

    id = db.Column(db.Integer, primary_key=True)
    announced_date = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(32))  # 地产/产业/贸易/货币
    level = db.Column(db.Integer, default=1)  # 对应政策信号分级 1/2/3
    description = db.Column(db.Text)


def seed_marker_exists() -> bool:
    """判断数据库里是否已经跑过种子数据，避免重复灌入。"""
    return Variety.query.first() is not None
