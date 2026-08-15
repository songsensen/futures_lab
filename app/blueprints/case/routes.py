# -*- coding: utf-8 -*-
"""
案例库蓝图：案例列表（带筛选）+ 案例详情两个页面。

这个蓝图本身不做任何"分析"，纯粹是 Case 表（以及它关联的 CaseTimeline/FactorTag/Variety）
的展示层——真正的情景匹配打分逻辑在 app/analysis.py 的 match_historical_cases 里，
那边算出"哪些案例跟当前品种相关"之后，才会链接到这里的 case_detail 页面看案例全貌。
"""
from flask import Blueprint, render_template, abort, request

from app.models import Case, Variety, FactorTag

case_bp = Blueprint("case", __name__)


@case_bp.route("/")
def case_list():
    """
    案例列表页，支持三个可选的 URL 查询参数筛选（?variety=SA&factor=3&origin=催生型），
    每个下拉框选完用 onchange="this.form.submit()" 直接刷新页面，不需要额外的搜索按钮。
    三个筛选条件是"与"的关系（同时满足才会出现在结果里），不是"或"。
    """
    variety_code = request.args.get("variety")
    factor_id = request.args.get("factor", type=int)
    origin = request.args.get("origin")

    query = Case.query
    if variety_code:
        v = Variety.query.filter_by(code=variety_code).first()
        if v:
            query = query.filter_by(variety_id=v.id)
    if factor_id:
        query = query.filter_by(event_type_id=factor_id)
    if origin:
        # origin 只有两个合法值："催生型"（事前有征兆，值得找规律）和"外生冲击型"
        # （真正随机的外部冲击，事前不可预判）——具体定义见 models.py 里 Case.trigger_origin 的注释。
        query = query.filter_by(trigger_origin=origin)

    cases = query.order_by(Case.start_date.desc()).all()
    # 筛选框本身的候选项永远是"全部品种/全部因素标签"，不随当前筛选结果变化，
    # 所以这两个查询不受上面 query 的筛选条件影响，是独立查询。
    varieties = Variety.query.order_by(Variety.code).all()
    factors = FactorTag.query.order_by(FactorTag.category, FactorTag.name).all()

    return render_template(
        "case/case_list.html", cases=cases, varieties=varieties, factors=factors,
        current_variety=variety_code, current_factor=factor_id, current_origin=origin,
    )


@case_bp.route("/<int:case_id>")
def case_detail(case_id):
    """
    案例详情页：事前状态、触发事件、当时基本面状态、市场解读vs真实驱动、
    最终结果与规律提炼、关键节点时间线，全部来自 Case 单表 + 关联的 CaseTimeline。
    """
    case = Case.query.get(case_id)
    if not case:
        abort(404)
    # lessons 字段是一段用换行分隔的自由文本（"不超过3条，换行分隔"，参见 models.py 里的注释），
    # 这里拆成列表方便模板用 <li> 渲染成真正的列表，而不是把换行符原样显示成一段文字。
    lessons = [l.strip() for l in (case.lessons or "").split("\n") if l.strip()]
    # diverges 标记"市场当时怎么解读"和"复盘后判断的真实驱动"这两个字段内容是否不一样——
    # 这两者故意拆成两个独立字段（而不是合并成一条"事件描述"），因为不一致的案例恰恰最有参考
    # 价值（对应"叙事 vs 真实驱动"的讨论），这里只是做字符串比较，不做任何语义判断。
    diverges = bool(
        case.market_interpretation_then
        and case.real_driver_after_review
        and case.market_interpretation_then.strip() != case.real_driver_after_review.strip()
    )
    return render_template("case/case_detail.html", case=case, lessons=lessons, diverges=diverges)
