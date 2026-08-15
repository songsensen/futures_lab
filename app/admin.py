# -*- coding: utf-8 -*-
"""
人工维护表的录入后台 —— /admin

覆盖范围：日线行情/持仓龙虎榜/仓单/基差/宏观数据这五张高频时间序列表不在这里，
它们走 app/data_import.py 的 CSV 批量导入（原因见该文件顶部说明：适合"整批追加"，
不适合一条条在网页表单里点）。这里覆盖其余所有表——不管是需要人工写文字判断的
（案例、事前状态、生产端工艺、产业链），还是虽然结构简单但更新频率低、需要人工
建档的（品种、合约、因素标签、月度利润率）。

用的是 Flask-Admin 现成的 SQLAlchemy ModelView —— 每张表自动生成列表/新增/编辑/删除
页面，外键字段自动渲染成下拉框，不用为每张表手写表单/路由。

注意：目前没有做登录鉴权，任何能访问这台机器上 /admin 路径的人都能改数据
（对应 models.py 里"owner_id 先留空，不做用户系统"的设计——以后要加鉴权，
在 register_admin 里给 Admin() 传一个自定义 AdminIndexView 做权限校验即可，
不需要改下面这些 ModelView 本身）。
"""
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme

from app.extensions import db
from app.models import (
    Variety, ProductionRoute, SupplyChainNode, FactorTag, VarietyFactor,
    Contract, Case, CaseTimeline, SetupEpisode, ProfitMarginRecord, Event, Policy,
)


class BaseAdmin(ModelView):
    page_size = 50
    can_export = True
    column_default_sort = None


class VarietyAdmin(BaseAdmin):
    column_list = ["code", "name", "exchange", "sector", "pricing_type", "profit_status", "storability"]
    column_labels = {
        "code": "代码", "name": "名称", "exchange": "交易所", "sector": "板块", "unit": "交易单位",
        "tick_size": "最小变动价位", "contract_months": "合约月份", "pricing_type": "定价权归属类型",
        "anchor_benchmark": "核心锚定标的", "linkage_coefficient": "内外盘联动系数",
        "cost_note": "成本说明", "import_cost_note": "进口成本参考", "profit_status": "当前盈利状态",
        "historical_low": "历史低点", "historical_high": "历史高点", "intro": "品种介绍",
        "storability": "库存耐储存性", "storability_note": "库存特性说明",
    }
    form_excluded_columns = ["factors", "contracts", "cases", "production_routes", "supply_chain_nodes"]
    column_searchable_list = ["code", "name"]


class ProductionRouteAdmin(BaseAdmin):
    column_list = ["variety", "route_name", "route_type", "market_share_pct", "cash_cost",
                   "produces_only_this", "byproduct_name"]
    column_labels = {
        "variety": "所属品种", "route_name": "工艺/产地名称", "route_type": "类型（工艺/原料产地）",
        "market_share_pct": "当前市场占比(%)", "cash_cost": "现金成本",
        "produces_only_this": "是否只产该品种（无则说明有副产品）",
        "byproduct_name": "副产品名称", "byproduct_profit_note": "副产品盈利状况及对主产品成本支撑的说明",
        "note": "备注",
    }


class SupplyChainNodeAdmin(BaseAdmin):
    column_list = ["variety", "direction", "order_index", "name", "cost_share_pct"]
    column_labels = {
        "variety": "所属品种", "direction": "方向（upstream上游 / downstream下游）",
        "order_index": "展示顺序（越小越靠近该品种）", "name": "节点名称",
        "cost_share_pct": "成本/需求占比(%)", "note": "备注",
    }


class FactorTagAdmin(BaseAdmin):
    column_list = ["name", "category", "description"]
    column_labels = {"name": "标签名称", "category": "类别（供应端/需求端/宏观）", "description": "说明"}
    column_searchable_list = ["name"]


class VarietyFactorAdmin(BaseAdmin):
    column_list = ["variety", "factor_tag", "importance_rank", "current_status", "status_updated_on"]
    column_labels = {
        "variety": "品种", "factor_tag": "因素标签", "importance_rank": "重要性(1-5，5最重要)",
        "monitoring_note": "监测要点（具体看什么指标/渠道）", "current_status": "现状（平静/偏热/异常）",
        "status_updated_on": "状态更新日期",
    }


class ContractAdmin(BaseAdmin):
    column_list = ["variety", "contract_code", "is_main"]
    column_labels = {"variety": "所属品种", "contract_code": "合约代码", "is_main": "是否主力连续"}
    form_excluded_columns = ["daily_bars", "position_ranks", "warehouse_receipts", "basis_records"]


class ProfitMarginRecordAdmin(BaseAdmin):
    column_list = ["variety", "period", "margin_value"]
    column_labels = {"variety": "品种", "period": "月份（用当月1号代表）", "margin_value": "利润率数值（越低越亏）"}


class CaseAdmin(BaseAdmin):
    column_list = ["variety", "name", "start_date", "end_date", "is_failure_case", "trigger_origin"]
    column_labels = {
        "variety": "品种", "name": "案例名称", "start_date": "开始日期", "end_date": "结束日期",
        "price_start": "起始价", "price_extreme": "峰/谷值", "price_end": "结束价",
        "event_type": "主驱动因素标签", "event_description": "事件描述（精确时间+精确措辞）",
        "market_interpretation_then": "市场当时主流解读", "real_driver_after_review": "复盘后真实驱动",
        "inventory_level_then": "当时库存水平（高位/中位/低位）", "demand_status_then": "当时需求状况（旺盛/正常/疲弱）",
        "profit_status_then": "当时盈利状况（盈利/盈亏平衡/亏损）", "final_price_landing": "最终价格落点说明",
        "policy_materialized": "政策/事件是否真正落地", "lessons": "规律提炼（不超过3条，换行分隔）",
        "is_failure_case": "是否失败案例（逻辑没兑现）", "pricing_regime_then": "当时定价权归属状态",
        "trigger_origin": "触发来源（催生型/外生冲击型）", "precipitating_mechanism": "催生机制",
        "setup_start_date": "事前状态起点日期（通常远早于开始日期）",
        "setup_description": "事前状态描述（价格/利润/库存已处于什么状态、持续多久）",
        "pre_event_chip_anomaly": "事件公开前的持仓/仓单/成交量异常说明",
    }
    form_excluded_columns = ["timeline"]
    column_searchable_list = ["name"]


class CaseTimelineAdmin(BaseAdmin):
    column_list = ["case", "event_date", "stage", "price"]
    column_labels = {
        "case": "所属案例", "event_date": "日期", "price": "价格",
        "stage": "阶段（预期炒作期/情绪消退期/现实回归期）", "description": "说明",
    }


class SetupEpisodeAdmin(BaseAdmin):
    column_list = ["variety", "dimension", "mechanism", "period_start", "period_end", "led_to_case"]
    column_labels = {
        "variety": "品种", "dimension": "观察维度（价格/利润）", "mechanism": "催生机制",
        "period_start": "极端状态开始日期", "period_end": "极端状态结束/被打断日期",
        "extreme_percentile": "当时历史百分位", "duration_days": "持续天数",
        "pre_event_signal": "观察到的具体信号（亏损时长、筹码异常等）",
        "led_to_case": "是否催生了案例（留空=历史上到过极端但没催生事件的反例）",
        "note": "备注（留空为反例时必须说明后来实际情况，不能不填）",
    }


class EventAdmin(BaseAdmin):
    column_list = ["variety", "event_date", "title", "level", "case"]
    column_labels = {
        "variety": "品种（留空=全市场宏观事件）", "event_date": "日期", "title": "标题", "description": "说明",
        "factor_tag": "因素标签", "level": "分级（1喊话预期/2具体措施/3基本面确认）", "source": "来源",
        "case": "关联案例（如果这条事件是某案例的锚点）",
    }
    column_searchable_list = ["title"]


class PolicyAdmin(BaseAdmin):
    column_list = ["announced_date", "name", "category", "level"]
    column_labels = {
        "announced_date": "发布日期", "name": "政策名称", "category": "类别（地产/产业/贸易/货币）",
        "level": "分级", "description": "说明",
    }
    column_searchable_list = ["name"]


def register_admin(app):
    # endpoint 显式加 admin_ 前缀 —— flask-admin 默认按模型类名小写生成 blueprint 端点名，
    # 会和已有的 case/main 等业务蓝图撞名（比如 Case 模型默认端点是 "case"，
    # 正好和 app/blueprints/case 这个蓝图同名），必须手动指定成唯一值。
    admin = Admin(app, name="期货实验室 · 数据管理后台", theme=Bootstrap4Theme(), url="/admin")
    admin.add_view(VarietyAdmin(Variety, db.session, name="品种", endpoint="admin_variety", category="品种基础信息"))
    admin.add_view(ProductionRouteAdmin(ProductionRoute, db.session, name="生产端工艺/产地", endpoint="admin_production_route", category="品种基础信息"))
    admin.add_view(SupplyChainNodeAdmin(SupplyChainNode, db.session, name="上下游产业链", endpoint="admin_supply_chain_node", category="品种基础信息"))
    admin.add_view(FactorTagAdmin(FactorTag, db.session, name="因素标签", endpoint="admin_factor_tag", category="品种基础信息"))
    admin.add_view(VarietyFactorAdmin(VarietyFactor, db.session, name="品种关注点", endpoint="admin_variety_factor", category="品种基础信息"))
    admin.add_view(ContractAdmin(Contract, db.session, name="合约", endpoint="admin_contract", category="行情"))
    admin.add_view(ProfitMarginRecordAdmin(ProfitMarginRecord, db.session, name="月度利润率", endpoint="admin_profit_margin_record", category="行情"))
    admin.add_view(CaseAdmin(Case, db.session, name="历史案例", endpoint="admin_case", category="案例库"))
    admin.add_view(CaseTimelineAdmin(CaseTimeline, db.session, name="案例时间线", endpoint="admin_case_timeline", category="案例库"))
    admin.add_view(SetupEpisodeAdmin(SetupEpisode, db.session, name="事前状态观察", endpoint="admin_setup_episode", category="案例库"))
    admin.add_view(EventAdmin(Event, db.session, name="事件", endpoint="admin_event", category="事件与政策"))
    admin.add_view(PolicyAdmin(Policy, db.session, name="政策", endpoint="admin_policy", category="事件与政策"))
    return admin
