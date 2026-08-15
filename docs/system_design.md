系统设计说明（大宗商品期货分析系统）

本文档面向以后独立维护这个项目的你自己，目标是"不用再问AI也能看懂整个系统"。内容包括：
整体架构、完整数据模型、分析引擎里每一个计算/统计的具体算法、每个页面的布局结构、
已知的限制和设计取舍、以及日常维护操作。代码本身也补充了大量中文注释，本文档和代码注释
互相印证——文档讲"为什么这么设计"和"全局怎么串起来"，代码注释讲"这一行/这个函数具体做什么"。



目录





设计哲学



技术栈与项目结构



完整数据模型



数据录入的三条通道



分析引擎详解（app/analysis.py）



路由与页面详解



前端图表实现要点



已知限制与设计取舍



日常维护操作



如果要继续往下做，参考优先级



1. 设计哲学

这套系统不是一个"预测涨跌"的黑箱模型，从最开始就贯彻几条刻意的设计原则，理解这几条
比记住任何具体代码都重要，因为后面所有模块的取舍都是从这几条推出来的：

宁可不凑，也不硬给结果。 情景匹配找不到相关案例就返回空列表、如实说"没有找到"；
历史转化率算不出来就返回 None；这些地方绝不为了页面好看去降低匹配门槛硬凑一条不相关的
案例出来。对应到代码里就是 MIN_MATCH_SCORE 这类阈值判断，以及每个"可能返回 None/空"
的函数上面都写清楚"什么时候会拿不到数据、为什么"。

诚实的基础概率，而不是暗示必然性。 SetupEpisode 表故意同时存"后来真的催生了事件"
的正例和"同样极端但什么都没发生"的反例，这样算出来的"历史转化率"才是诚实的基础比率，
而不是只挑正例、让人误以为"极端了就一定会反转"。这个原则贯穿了事前状态信号、案例匹配、
风险回报参考这几个模块。

事件是果，不一定是因。 很多行情不是随机外生冲击，而是价格/利润/筹码走到极端后被动
"挤"出来的结果。系统专门把"事前状态"（SetupEpisode、compute_setup_signal 等）和
"事件本身"（Event、Case）拆成两层，试图往前找到比新闻更早的信号，而不是等新闻发生
了才反应。

市场当时的解读，不等于真实驱动。 Case 表故意把 market_interpretation_then（市场
当时怎么解读）和 real_driver_after_review（复盘后判断的真实驱动）拆成两个独立字段，
两者不一致的案例反而最有参考价值——这是在提醒"当时大家都这么说"不代表"这就是真相"。

决策参考不等于决策。 最新加的"信号对齐"和"风险回报参考"，出发点是把原本需要交易员
自己在脑子里综合的几路独立证据摆到一起，但结论用词非常克制（"多头因素占优"而不是
"买入信号"），每处都带着"不构成投资建议、不保证未来重复历史"的说明。系统的定位始终是
证据整理和参照系统，最终判断和风险留给使用者自己。



2. 技术栈与项目结构





后端：Flask 3.x + Flask-SQLAlchemy（ORM）+ SQLite（单文件数据库，instance/futures_lab.db）



后台管理：Flask-Admin（/admin，用于人工维护的表）



前端：Jinja2 服务端模板 + Bootstrap 5（本地 vendor，无需联网）+ ECharts（本地 vendor，K线/走势图）



数据导入：Flask CLI 命令（flask import-xxx），处理时间序列类数据的批量导入



无前端构建流程：没有 npm/webpack，所有 JS 直接内嵌在 Jinja 模板的 <script> 标签里，
改页面逻辑不需要构建步骤，改完刷新页面就是最新代码。

futures_lab/
├── run.py                  # 本地启动入口：python run.py（会自动建库+灌种子数据）
├── seed_db.py              # 手动重建数据库并重灌种子数据：python seed_db.py --reset
├── config.py               # 配置（SECRET_KEY、数据库连接串）
├── requirements.txt        # 依赖清单
├── instance/               # SQLite 数据库文件所在目录（.gitignore 掉，不进版本控制）
├── import_templates/       # 时间序列表 CSV 导入模板 + 用法说明
├── docs/                   # 本文档 + admin后台录入说明
└── app/
    ├── __init__.py         # create_app() 工厂函数：初始化DB、注册蓝图、注册CLI、注册admin
    ├── extensions.py       # 全局唯一的 db = SQLAlchemy() 实例，避免循环import
    ├── models.py           # 全部17张表的定义（详见第3节）
    ├── seed.py             # 生成测试/演示数据的脚本（品种/行情/案例/事件全部是模拟数据）
    ├── analysis.py         # 分析引擎：所有统计计算、信号判断、案例匹配逻辑（详见第5节）
    ├── data_import.py      # 时间序列表的 CSV 批量导入函数（upsert逻辑）
    ├── cli.py              # 把 data_import.py 的函数包成 flask 命令行命令
    ├── admin.py            # Flask-Admin 后台配置（哪些表可以在网页上增删改查）
    ├── blueprints/         # 按功能拆分的5个蓝图（详见第6节）
    │   ├── main/           # 品种列表 + 品种详情页（核心页面，信息量最大）
    │   ├── case/           # 历史案例库列表 + 详情
    │   ├── calendar/       # 事件+政策合并时间线
    │   ├── position/       # 持仓/仓单走势图（品种详情页摘要卡片的展开版）
    │   └── principles/     # 静态的交易原则清单
    ├── templates/          # Jinja2 模板，目录结构和 blueprints 一一对应
    └── static/
        ├── css/style.css   # 全站自定义样式（很薄，13行，主要是状态徽章配色）
        └── vendor/         # 本地化的 Bootstrap、ECharts（不依赖 CDN，离线也能跑）



3. 完整数据模型

全部定义在 app/models.py 一个文件里。下面按模块列出每张表的字段和关系；更偏"怎么在
/admin 里录入"的说明见 docs/admin_guide.md，这里侧重"字段含义 + 关系 + 是否被分析引擎
使用"。

3.1 品种基础信息模块

variety（品种） — 全系统唯一的中心表，其余几乎所有表都通过 variety_id 直接或间接
挂在它下面。







字段



说明





code / name



品种代码/名称（如 SA / 纯碱）





exchange / sector



交易所 / 板块





unit / tick_size / contract_months



交易单位、最小变动价位、合约月份





pricing_type



定价权归属类型：进口依赖型 / 国内供需型 / 全球金融属性型





anchor_benchmark / linkage_coefficient



核心锚定标的、内外盘联动系数 —— 目前只在页面上展示，没有被 analysis.py 任何函数实际计算使用，是个已知的"有数据没接入逻辑"的字段，见第8节





cost_note / import_cost_note / profit_status



成本区间说明、进口成本参考、当前盈利状态





historical_low / historical_high



历史高低点（目前是静态字段，不是从 DailyBar 动态算出来的）





storability / storability_note



库存耐储存性（耐储存/不耐储存/中等）及说明——用于判断"库存高企"这个信号对不同品种的含义和持续性是否一样

production_route（生产端工艺/产地）：variety_id 外键。工业品对应不同工艺路线，农产品
对应不同原料产地，本质都是"同一品种背后有几条并行、成本结构不同的生产路径"，所以共用一张表。
字段：route_name、route_type（工艺/原料产地）、market_share_pct（当前市场占比）、
cash_cost（现金成本）、produces_only_this（是否只产该品种）、byproduct_name /
byproduct_profit_note（副产品名称及其盈利状况——副产品还盈利的话，主产品低价能维持更久，
这是判断"跌破成本还能撑多久"时容易被忽略的变量）。

supply_chain_node（上下游产业链节点）：variety_id 外键。direction 区分 upstream/
downstream，order_index 控制展示顺序，cost_share_pct 含义随方向变化（上游=占该品种
生产成本的比例，下游=该品种占下游产品成本的比例，两个方向的数字不能跨节点相加）。

factor_tag（因素标签）：不挂品种，是全局共享的标签库（如"政策喊话""天气异常""逼仓"），
category 分供应端/需求端/宏观。被 variety_factor、case.event_type_id、
event.factor_tag_id 三处引用，是"品种关注点"和"历史案例"能互相检索的关键接口。

variety_factor（品种关注点清单）：variety_id + factor_tag_id 外键。importance_rank
（1-5）、monitoring_note（具体该看什么指标）、current_status（平静/偏热/异常，由
compute_factor_status() 动态计算写出，不是存在库里的静态值——这个字段实际上每次请求都会
被后端重新计算覆盖显示，数据库里的值只是初始默认值）。

3.2 行情与筹码数据模块（时间序列，走 CSV 导入）

contract（合约）：variety_id 外键。当前是简化处理——每个品种只有一条
contract_code="XX.main"、is_main=True 的合成连续序列，不是真实的分合约拼接，没有
换月/复权逻辑（这个简化是刻意保留的产品决策，详见第8节）。

daily_bar（日线行情）：contract_id 外键，(contract_id, trade_date) 唯一约束。
open/high/low/close/settle/volume/open_interest。是K线图、均线、历史百分位、案例对比图
的底层数据源。

position_rank（持仓龙虎榜简化版）：contract_id 外键。total_open_interest、
top5_long_ratio、top5_short_ratio（前5多/空席位占比）——没有具体到单个席位，
只有汇总的多空集中度，这是"筹码信号目前比较浅"的根源之一（见第8节）。

warehouse_receipt（仓单日报）：contract_id 外键，receipt_qty。

basis（期现基差）：contract_id 外键，futures_price/spot_price/basis_value。

3.3 历史案例库模块

case（历史案例）：variety_id 外键，event_type_id 关联 factor_tag。核心字段：
start_date/end_date/price_start/price_extreme/price_end；
inventory_level_then/demand_status_then/profit_status_then（当时基本面状态分类，
情景匹配拿现状的同一套分类去对比）；market_interpretation_then vs
real_driver_after_review（故意拆开的两个字段，见第1节）；is_failure_case（标记"逻辑
没兑现"的案例，避免案例库幸存者偏差）；trigger_origin（催生型/外生冲击型）+
precipitating_mechanism（资金布局型/物极必反型/容忍阈值型）；setup_start_date（事前
状态真正开始的时间，通常远早于 start_date）。

case_timeline（案例关键节点时间线）：case_id 外键，event_date/price/stage
（预期炒作期/情绪消退期/现实回归期）/description。

setup_episode（事前状态观察记录）：variety_id 外键，led_to_case_id 外键到 case
且可以为空——为空代表"到过极端但什么都没发生"的反例，这是算诚实转化率的关键设计（见
第1节）。dimension（价格/利润）、mechanism、period_start/period_end、
duration_days、extreme_percentile。

profit_margin_record（月度利润率）：variety_id 外键，(variety_id, period) 唯一
约束。独立于价格分位数之外的另一条极端状态判断依据（见第5节 compute_margin_signal）。

3.4 事件与日历模块

event（事件）：variety_id 外键（可为空，宏观事件不特定于某品种）、
factor_tag_id 外键、case_id 外键（可为空，非空代表这条事件是某个案例的"锚点"，
即市场公开注意到这段行情的那个点）。level（1喊话/2具体措施/3基本面确认）。
服务于两处：品种详情页K线图上的标注点、日历时间线列表。

事件(Event) vs 案例(Case) 的关系：两者粒度完全不同。Event 是细粒度的"某天发生了
什么"记录，字段很薄，数量多；Case 是完整的一段行情复盘，字段厚得多，数量少。两者的连接点
是 event.case_id，且只能从 Event 这一侧设置——Case 没有反向关联 Event 的字段，
因为 Case 不需要在详情页里维护一份"哪些事件指向我"的清单。

3.5 宏观与政策监控模块

macro_data（宏观数据点）：indicator/report_date/value，(indicator, report_date) 唯一约束。当前完全没有被任何页面读取或显示，也没有接入任何信号计算
——种子数据里生成了 PMI/CPI同比/USDCNY 三个指标的月度序列，但整个系统里再没有第二处
代码引用过这张表。这是一个已知的"建了表、没通电"的模块（见第8节）。

policy（政策监控清单）：announced_date/name/category（地产/产业/贸易/货币）/
level。只在 calendar 蓝图里被读取用来拼进时间线列表展示，同样没有接入任何信号计算。

3.6 关系总图（文字版）

variety ──┬── production_route（生产端工艺/产地）
          ├── supply_chain_node（上下游产业链）
          ├── variety_factor ── factor_tag（因素标签，全局共享）
          ├── contract ──┬── daily_bar
          │              ├── position_rank
          │              ├── warehouse_receipt
          │              └── basis
          ├── profit_margin_record
          ├── case ──┬── case_timeline
          │          ↑（反向引用，均可为空）
          │       event.case_id          setup_episode.led_to_case_id
          └── event（variety_id 也可为空，代表宏观事件）

全局独立、不挂具体品种：factor_tag、macro_data、policy



4. 数据录入的三条通道

4.1 种子/演示数据（app/seed.py）

run_seed() 在数据库为空时自动跑一遍，生成 SA（纯碱）/FG（玻璃）/M（豆粕）三个品种的
全套模拟数据——包括价格走势、案例、事件、生产端工艺、产业链、利润率序列等等。这是
纯手工编造的演示数据，用来验证整个系统的逻辑链路能不能跑通，不是真实历史。
seed_marker_exists() 通过检查 Variety 表是否有数据来判断"是不是已经灌过了"，避免
重复灌入。

4.2 CSV 批量导入（真实数据的主要入口，针对时间序列表）

针对 daily_bar/position_rank/warehouse_receipt/basis/macro_data 这五张
"每天/每月追加一批新行"的表，用 flask import-xxx path/to/file.csv 命令导入，详细的列
格式和用法见 import_templates/README.md。核心设计：





全部走 upsert（按各表已有的唯一约束判断插入还是更新），重复导入同一份文件是安全的。



variety_code 必须是已存在的品种（不会自动创建，防止代码打错生成垃圾品种）；
contract_code 第一次出现会自动创建对应的 Contract 记录。



任何一行数据有问题（比如品种代码不存在）只会跳过那一行，不影响其余行导入，并把跳过的
行号和原因打印出来。

4.3 Flask-Admin 后台（人工维护的表）

针对案例库、事前状态、生产端工艺、产业链、事件、政策等需要人工判断/写文字说明的表，
在 /admin 提供网页表单增删改查。详细的录入顺序建议、表单字段说明、常见关系陷阱见
docs/admin_guide.md（专门写给"怎么用这个后台录数据"这个问题）。



5. 分析引擎详解（app/analysis.py）

这是整个系统的核心逻辑所在，所有统计计算和信号判断都在这一个文件里，函数之间没有隐藏的
全局状态，每个函数都是"给定输入，算出输出"的纯函数风格（除了查数据库）。下面按调用顺序
说明每个函数具体在算什么。

5.1 现状快照类函数





get_price_snapshot(variety)：取该品种主力合约的全部日线，算最新收盘价在历史全部
收盘价里的百分位排名（_percentile_rank，用"小于等于当前值的样本数 ÷ 总样本数"的定义，
0-100取整）。返回历史最高/最低价、完整 bars 列表（供K线图用）。



get_position_snapshot(variety)：持仓量历史百分位、虚实盘比（总持仓量 ÷ 最新 仓单量），虚实盘比超过100:1标记警戒（virtual_real_alert）。



get_basis_snapshot(variety)：最新基差值，basis_value < 0 记为"升水"，否则"贴水"
（注意这里的正负号约定：basis_value 是"现货-期货"，正值代表现货比期货贵，即期货贴水；
这个符号约定和字面直觉可能相反，改这块代码前务必先确认 Basis.basis_value 的定义）。

5.2 现状体检（compute_factor_status）

给品种关注点清单（VarietyFactor）里每一条，算一个"现在是不是活跃"的状态：





最近 RECENT_EVENT_WINDOW_DAYS（60天）内有没有命中同一因素标签的 Event，有的话按

命中事件的最高 level 决定是"异常"（level≥3）还是"偏热"；



没有命中事件，但价格百分位处于 ≤10% 或 ≥90% 的极端区间，也给"偏热"提示；



否则是"平静"。

这是一个规则过滤器，不是智能判断——纯粹是"最近有没有事、价格是否极端"这两条硬编码
规则，注释里也明确写了这一点，避免以后误以为这里有什么机器学习模型。

5.3 三条独立的"事前状态"信号通道

这三条通道刻意保持互相独立，分别捕捉三种不同的"极端"：

compute_setup_signal(variety) —— 价格维度：用 _expanding_percentile_series()
逐日计算"只用当天及之前数据"算出的历史百分位（避免用未来数据判断过去的前视偏差），
至少要有 SETUP_MIN_WINDOW（60个交易日）数据才开始算。最新一天百分位 ≤10% 记"低位"，
≥90% 记"高位"，并往回数这个极端状态已经连续持续了多少个交易日（streak_days）。

compute_margin_signal(variety) —— 利润/成本维度：逻辑和价格维度完全一样，但换成
月度利润率序列（ProfitMarginRecord），MARGIN_MIN_WINDOW＝12个月。存在这条通道的原因：
价格没有历史极端，不代表基本面没有走极端——成本端变化可能让利润率独立地陷入历史极值。

compute_chip_anomaly_signal(variety) —— 筹码异常（资金布局型）：不看价格所处
位置，任何价格水平下都检查：





持仓量最近 CHIP_LOOKBACK_DAYS（20个交易日）的变化率（_rate_of_change_series），
是否处于历史分位 ≥95% 或 ≤5%（oi_direction：异常放大/异常萎缩）；



仓单同样逻辑（wh_direction：骤增/骤减）；



虚实盘比是否超过100:1。
命中任意一条就标记 triggered=True。oi_direction 不带经济学方向（持仓量变大
可能是新多也可能是新空），所以后面的复合信号只采纳 wh_direction（仓单是真实的可交割
库存，变多=供应压力=偏空，变少=偏多）。

match_setup_precedents(variety, setup_signal, dimension) 拿"当前已经持续多久"去匹配
SetupEpisode 历史库，按持续天数分桶（streak*0.4 到 max(streak*2.5, 30) 天的范围，
找不到就放宽成全部历史样本并标注 used_fallback），返回可比样本数、催生事件数、转化率——
这个转化率同时统计了正例和反例，是诚实基础比率，不是"极端了就一定反转"的暗示。

5.4 历史案例匹配（match_historical_cases）

打分制，不是相似度向量或机器学习模型，规则完全写死、可解释：







命中条件



加分





案例的驱动因素标签，正好是当前"偏热/异常"的因素之一



+2





当前价格位置桶（高位/中位/低位）与案例的库存状态桶用一个粗代理映射后一致



+1





案例本身发生在同一品种上



+1





案例对应的 SetupEpisode 维度(价格/利润)，正好是当前实际触发的那条通道



+2





案例对应的 SetupEpisode 机制是"资金布局型"，且当前筹码通道也触发了



+2

低于 MIN_MATCH_SCORE（2分）的直接过滤掉，不展示；同时如实统计"因为分数不够被筛掉
多少条"（below_threshold），避免用户误以为算法只找到这么几条相关案例。返回
(scored[:top_n], below_threshold) 元组。_score_label() 把原始分数换算成"强匹配/
中等匹配/弱匹配"标签，避免让人猜"4分算不算高"。

get_case_precedent_stats(case) 给已匹配上的案例，反查它对应的 SetupEpisode，再拿
"同品种、同维度、持续天数量级相近（0.4x~2.5x区间）"的全部历史样本算一次转化率，在对比图
旁边给一句"这类前置状态历史上有多大概率真的催生了事件"，防止"形状像"这个视觉暗示单方面
让人以为历史一定重演。

5.5 案例对比序列生成（get_case_comparison_series）

核心方法论：两段行情（当前 vs 历史案例）价格水平、时间跨度都不同，直接摆在一起看
K线没有意义，所以：





各自以"day 0"当天收盘价为基准，把后续每天换算成相对 day 0 的百分比涨跌（pct 字段）；



历史案例的 day 0 = case.start_date（事件被市场注意到那天）；当前品种的 day 0 =

最新交易日（"现在"）；



两条序列在图上 x=0、y=0 处天然对齐，形状是否相似一眼就能看出来。

均线（MA5/10/20）用完整的合约历史先算好，再按显示窗口切片——不能反过来先截取窗口
再算均线，否则窗口最左边几根K线的均线会因为"看得到的历史不够"而失真（_moving_ average_series 的实现和调用顺序都要保持这个先后关系）。

如果案例有 setup_start_date（事前状态真正开始的时间，通常早于 start_date），显示
窗口会自动往前延伸以确保这段"提前量"在图上可见（setup_offset）；case_timeline 的
各个节点也会换算成同一套 offset 坐标返回（timeline_markers），供图表画三角标记。

5.6 风险回报参考（get_case_risk_reward / summarize_case_risk_reward）

从 get_case_comparison_series 已经算好的 case_series（历史案例的完整价格路径）里，
取 offset >= 0（也就是从"和现在对应的起点"开始往后）的所有 pct 值，直接取
max()/min()/最后一个值，分别对应"最大涨幅""最大回撤""最终涨跌"，offset 的最大值
就是"用了多少个交易日"。这几个数字全部来自真实历史价格路径，不是另外拍脑袋给的止损/
止盈建议。is_failure_case（逻辑没兑现的案例）这里刻意不做特殊处理——价格路径本身已经
如实反映了到底涨了还是跌了，不需要因为案例被标记为"未兑现"就跳过或反向处理这几个数字。

summarize_case_risk_reward 把多条匹配案例的风险回报数字汇总成区间（最小值~最大值），
不是取平均值掩盖分歧——不同案例的最大涨幅/回撤可能差异很大，展示区间比一个精确到小数点
的平均数更诚实。

5.7 决策参考：信号对齐（compute_composite_signal）

把前面几条独立信号的方向摆到一起对齐，不是一个训练出来的模型，是一份"信号对齐清单"：





价格分位：历史低位→偏多（均值回归逻辑），历史高位→偏空；不处于极端则不投票。



利润状态：利润极低→偏多（现金成本支撑逻辑），利润极高→偏空（超额利润吸引扩产逻辑）；
不处于极端则不投票。



筹码：只用仓单方向投票（骤增→偏空，骤减→偏多）；持仓量变化率异常不投票（原因见
5.3），只作为提示信息展示。



历史相似案例：把每条匹配案例的 price_end 相对 price_start 的涨跌方向，按匹配分
加权平均，>0.3 记偏多，<-0.3 记偏空，中间地带记"涨跌互现，不计入"。

汇总规则：统计偏多票数(bullish)和偏空票数(bearish)——





都是0 → "无明显方向"，置信度"低"；



两边都有票 → "多空信号不一致"，置信度"低"（这是刻意的：出现分歧时不应该装作有把握）；



只有一边有票 → "多头/空头因素占优"，票数≥3记"高"置信度，否则"中"。

返回结果永远带一个 caveat 字段，措辞是"这是历史统计意义上的方向对齐提示……不构成投资
建议，也不保证未来走势会重复历史"——这个字段和结论本身一样重要，模板里也是原样展示出来，
不能在改版时被精简掉。



6. 路由与页面详解

6.1 main 蓝图（/ 和 /variety/<code>）





variety_list：品种列表卡片，每张卡片带最新价、历史百分位。



variety_detail：信息量最大的页面，app/blueprints/main/routes.py 里这个视图函数
按顺序做了这些事：算三条事前状态信号 → 用这三条信号 + 现状体检结果去匹配历史案例 → 给
每条匹配案例算对比序列、前置状态转化率、风险回报参考 → 汇总出决策参考信号对齐 → 组装
K线图需要的数据 → 一次性传给模板。如果要新增一个信号维度，正确的加入顺序也应该是
"先算出信号 → 传入 match_historical_cases 让案例匹配也能用上它 → 再考虑要不要让
compute_composite_signal 采纳这条新方向"，而不是只在模板里加个新卡片展示了事。

页面卡片自上而下的顺序（这个顺序本身就是"决策参考优先，细节佐证在后"的信息架构决定）：

[决策参考·信号对齐]（全宽，跨越下面两栏）
├── 左栏(col-md-4)                    ├── 右栏(col-md-8)
│   品种基本信息/定价权/成本            │   历史K线（事件标注+MA+成交量/持仓量）
│   生产端工艺/产地对比                 │   事前状态信号·价格维度
│   上下游产业链与成本占比              │   事前状态信号·利润/成本维度
│   现状体检                           │   事前状态信号·筹码异常
│                                     │   关键关注点清单
│                                     │   历史相似案例参照（含风险回报、对比图）

6.2 case 蓝图（/case）





case_list：支持 ?variety=&factor=&origin= 三个筛选参数（与关系）。



case_detail：事前状态说明 → 触发事件 → 当时基本面状态 / 市场解读vs真实驱动（不一致会
高亮）→ 最终结果与规律提炼 → 关键节点时间线。

6.3 calendar 蓝图（/calendar）

把 Event 和 Policy 两张表拍平成统一结构、按日期倒序合并展示的一张表格，纯列表，
没有图表。

6.4 position 蓝图（/position）

position_index 品种入口列表 → position_detail 持仓量/仓单量走势图 + 虚实盘比走势图
（复用 get_position_snapshot/get_price_snapshot，没有独立的计算逻辑）。

6.5 principles 蓝图（/principles）

纯静态页面，PRINCIPLES 是硬编码在 routes.py 里的 Python 列表，没有数据库表。

6.6 admin（/admin，非蓝图，Flask-Admin 独立挂载）

见 docs/admin_guide.md。



7. 前端图表实现要点

全部基于本地 vendor 的 ECharts，没有用任何图表框架的 React/Vue 封装，纯手写
echarts.init() + setOption()。几个容易踩坑、已经在代码注释里写清楚的地方，这里再汇总
一遍：

ECharts 类目轴的 axisValue 在 tooltip 里永远是字符串，哪怕 xAxis.data 数组里存的
是数字。对比图的 tooltip 曾经因为这个坑显示 undefined（拿字符串去 indexOf 数字数组
永远找不到），修复方式是 Number(params[0].axisValue) 转型后再查找。

markArea/markLine 在类目轴上必须精确匹配 data 数组里存在的值，非交易日（比如
周末）没有精确匹配会静默不渲染。setup_regions（事前状态背景色块）用
nearestTradingDateOnOrAfter/nearestTradingDateOnOrBefore 把区间起止日期"吸附"到
最近的真实交易日上，再拿去画 markArea。

均线/成交量/持仓量默认走 ECharts 原生图例点击隐藏/显示，不需要额外写开关按钮逻辑，
只要把这几个 series 的 name 放进 legend.data 里即可。

成交量和持仓量共用一个 grid，但走双 y 轴（左轴管成交量，右轴管持仓量），因为两者数量级
差异很大（比如豆粕持仓量能到几十万手，成交量是另一个量级），这是本项目里少数刻意使用双
Y轴的地方（一般图表设计原则是避免双轴，这里是因为用户明确要求合并显示，且两者单位相同
都是"手"）。

K线对比图的 day 0 对齐：详见第5.5节的算法说明，前端只是把后端已经算好的 offset/
pct 字段直接拿来画，不在前端重新计算对齐逻辑。



8. 已知限制与设计取舍

这一节是最重要的部分之一——记录哪些是"暂时没做但知道该做"，哪些是"刻意决定不做"，
避免以后重新发现同一个问题却忘了当初为什么这样处理。

只有骨架/测试数据，只有3个品种。 案例库一共6条案例、8条事前状态记录。所有百分位、
转化率、信号对齐的结果目前都建立在这个很小的样本上，逻辑没问题，但数字本身经不起较真——
这是当前最大的限制，不接真实数据，这套系统始终只是逻辑演示。

复合信号/风险回报框架从未做过历史回测验证。 compute_composite_signal 和风险回报
参考的可信度目前完全来自"规则逻辑上讲得通"，从没有拿真实历史数据反过来验证过"如果照着
这套规则交易，历史上是不是真的能赚钱"。这是本系统目前最大的信任缺口。

宏观(MacroData)和政策(Policy)模块基本是摆设。 MacroData 表种了数据但没有任何页面
读取、没有接入任何信号计算；Policy 只在日历页面列出来，同样没有参与打分。Variety 的
anchor_benchmark/linkage_coefficient 字段同理，只在页面上展示，从未被拿去和真实的
外部基准价格做过计算。

筹码信号比较浅。 只有总持仓量变化率、仓单变化率、虚实盘比三个汇总指标，没有具体到
单个席位的增减仓明细（position_rank 表只存了前5多空集中度这两个汇总比例）。

主力合约是简化的连续合成序列，不是真实分合约拼接。 没有真实的合约到期/换月逻辑，
Contract 表里每个品种永远只有一条 is_main=True 的记录。这是经过讨论后刻意决定
暂缓的简化（见对话记录），如果以后接真实数据需要处理换月，得重新设计成"真实分合约 +
主力合约切换时间表"这套结构，工作量不小。次主力合约（同期成交量/持仓量第二活跃的合约）
同样没有建模。

没有自动化测试。 这几个月的所有改动都是靠手工截图、手工查库、Playwright 脚本临时
验证，项目里没有 test_*.py，analysis.py 里这些百分位计算、评分规则、日期对齐逻辑
如果以后重构，没有回归测试兜底。

/admin 没有登录鉴权。 任何能访问这台机器上 /admin 路径的人都能改数据。目前是
单机单用户使用，暂时没做；models.py 里预留了 owner_id 的设计空间，以后要加用户系统
不需要推翻现有表结构。

还在用 Flask 开发服务器（app.run(debug=True)），不是生产级部署，SQLite 单文件
数据库也没有备份机制。

没有推送/主动提醒机制。 系统完全是"你点进页面才能看到当前信号"，信号真正变得极端的
那一刻不会主动通知你。

没有仓位/资金管理层面的换算。 风险回报参考给的是价格百分比，不是"根据你的账户规模/
风险承受度应该开多少仓"——这一点某种程度上是系统本来就做不到的事（系统不知道你的资金
情况），不完全算是待办事项，但要清楚这个边界。



9. 日常维护操作

改了 models.py 之后必须重建数据库（Flask-SQLAlchemy 的 db.create_all() 只会
创建不存在的表，不会给已存在的表加字段/改字段），操作：

rm instance/futures_lab.db
python3 seed_db.py --reset

启动本地开发服务器：

python3 run.py
# 或者要避免旧进程占用端口时：
fuser -k 5000/tcp   # 先释放5000端口
python3 run.py

⚠️ 用 pkill -f run.py 杀进程时要小心：如果这条命令本身是通过某种"把整段命令文本传给
shell执行"的方式跑的（比如某些自动化工具），pkill -f 会按子串匹配所有进程的完整命令行，
可能连自己所在的这个shell进程都一起杀掉，导致命令莫名其妙"卡住"或"提前中断、后面的命令
没执行"。更安全的做法是用 fuser -k 5000/tcp（按端口杀）或者先 ps aux | grep run.py
拿到精确 PID 再 kill <pid>。

导入真实数据（时间序列表）：见 import_templates/README.md，核心命令
flask --app run.py import-daily-bar path/to/file.csv（五张表各有一条对应命令）。

录入案例/事件/生产端等人工维护数据：打开 http://localhost:5000/admin/，详细顺序
见 docs/admin_guide.md。

新增一个品种：先在 /admin 建 Variety 记录，拿到品种代码后，行情数据走 CSV 导入
命令（会自动创建对应的 Contract），其余画像类数据（生产端/产业链/关注点/案例等）走
/admin 逐条补充。

添加一条新的信号维度（比如接入真实的宏观数据）：参考 compute_margin_signal 或
compute_chip_anomaly_signal 的写法（独立计算函数，返回一个带 direction/
in_extreme_zone 之类字段的 dict），然后在 main/routes.py 的 variety_detail 里
调用它、把结果传给 match_historical_cases（如果要参与案例匹配）和
compute_composite_signal（如果要参与多空对齐投票），最后在模板里加一张展示卡片。



10. 如果要继续往下做，参考优先级

这不是待办清单，只是把之前讨论过的优先级顺序记录下来，方便以后回看：





接入至少一两个品种的真实历史数据——这是一切的前提，不接真实数据，后面的验证都无从谈起。



拿信号对齐/案例匹配逻辑做一次历史回测——验证"如果历史上照着这套规则走，是否真的

有效"，而不是停留在"逻辑讲得通"。



宏观(MacroData)/政策(Policy)真正接入信号计算，而不是摆设。



筹码信号细化到具体席位增减仓（如果能拿到更细的数据源）。



主力合约的真实换月建模（含次主力合约），只有在真的要接实盘数据时才有必要动。



工程层面：补自动化测试、/admin 加鉴权、换生产级部署方式、加推送提醒机制。

