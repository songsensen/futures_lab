# -*- coding: utf-8 -*-
"""
日历/时间线蓝图：把 Event（品种事件）和 Policy（政策监控）这两张本来毫不相关的表，
合并成一条按日期倒序的统一时间线列表——用户想看的是"最近发生了什么"，不关心这条信息
底层来自哪张表，所以在这一层把两者拍平成同一种 dict 结构再一起排序，而不是分两个列表
展示逼着用户自己在脑子里按时间交叉对照。

注意：Policy 表目前只在这一个地方被读取、展示，没有被 app/analysis.py 的任何信号计算
使用——政策监控目前是纯粹的"人工浏览清单"，还没有接入自动化的分析逻辑。
"""
from flask import Blueprint, render_template

from app.models import Event, Policy

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/")
def calendar_view():
    events = Event.query.order_by(Event.event_date.desc()).all()
    policies = Policy.query.order_by(Policy.announced_date.desc()).all()

    # 把 Event 和 Policy 两种不同结构的记录，统一转成同一套字段名(date/title/type/variety/
    # factor/level/description)，这样后面排序、模板渲染都只需要认一种结构，不用对每种来源
    # 各写一套模板逻辑。variety 这一列对 Policy 来说其实放的是 category（地产/产业/贸易/货币），
    # 语义上不完全是"品种"，只是复用同一个显示位置，模板里用 type 徽章区分两者。
    items = []
    for e in events:
        items.append({
            "date": e.event_date, "title": e.title, "type": "品种事件",
            "variety": e.variety.name if e.variety else "—",
            "factor": e.factor_tag.name if e.factor_tag else "",
            "level": e.level, "description": e.description,
        })
    for p in policies:
        items.append({
            "date": p.announced_date, "title": p.name, "type": "政策监控",
            "variety": p.category, "factor": "", "level": p.level, "description": p.description,
        })
    items.sort(key=lambda x: x["date"], reverse=True)

    return render_template("calendar/calendar_list.html", items=items)
