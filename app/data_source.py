import akshare as ak
import time
from datetime import date, timedelta

# if __name__ == '__main__':


#     futures_zh_daily_sina_df = ak.futures_zh_daily_sina(symbol="SA0")
#     print(futures_zh_daily_sina_df)

#     for index, row in futures_zh_daily_sina_df.iterrows():
#         da = row['date']
#         open = row['open']
#         high = row['high']
#         low = row['low']
#         close = row['close']
#         volume = row['volume']
#         open_interest = row['hold']
#         settle = row['settle']

#         s = f'{da} -- {open} -- {high} -- {low} -- {close} -- {volume} -- {open_interest} -- {settle}'
#         print(s)


    # df = ak.futures_display_main_sina()
    # for index, row in df.iterrows():
    #     # print(row)
    #     symbol = row['symbol']
    #     name = row['name']
    #     exchange = row['exchange']
    #     s = f"{symbol} --- {name} --- {exchange}"
    #     print(s)


    # today = date.today()                        # 当前日期
    # start_day = today - timedelta(days=3)       # 前三天

    # start_str = start_day.strftime("%Y%m%d")    # '20260908'
    # end_str   = today.strftime("%Y%m%d")        # '20260911'

    # futures_spot_price_daily_df = ak.futures_spot_price_daily(start_day=start_str, end_day=end_str, vars_list=["SA"])
    # print(futures_spot_price_daily_df)
    # print(futures_spot_price_daily_df.columns)


    # get_rank_sum_daily_df = ak.get_rank_sum_daily(start_day="20260908", end_day="20260911", vars_list=["RB"])
    # print(get_rank_sum_daily_df)
    # print(get_rank_sum_daily_df.columns)




# V0 --- PVC连续 --- dce
# P0 --- 棕榈油连续 --- dce
# B0 --- 豆二连续 --- dce
# M0 --- 豆粕连续 --- dce
# I0 --- 铁矿石连续 --- dce
# JD0 --- 鸡蛋连续 --- dce
# L0 --- 塑料连续 --- dce
# PP0 --- 聚丙烯连续 --- dce
# FB0 --- 纤维板连续 --- dce
# Y0 --- 豆油连续 --- dce
# C0 --- 玉米连续 --- dce
# A0 --- 豆一连续 --- dce
# J0 --- 焦炭连续 --- dce
# JM0 --- 焦煤连续 --- dce
# CS0 --- 淀粉连续 --- dce
# EG0 --- 乙二醇连续 --- dce
# RR0 --- 粳米连续 --- dce
# EB0 --- 苯乙烯连续 --- dce
# PG0 --- 液化石油气连续 --- dce
# LH0 --- 生猪连续 --- dce
# LG0 --- 原木连续 --- dce
# BZ0 --- 纯苯连续 --- dce
# TA0 --- PTA连续 --- czce
# OI0 --- 菜油连续 --- czce
# RS0 --- 菜籽连续 --- czce
# RM0 --- 菜粕连续 --- czce
# WH0 --- 强麦连续 --- czce
# JR0 --- 粳稻连续 --- czce
# SR0 --- 白糖连续 --- czce
# CF0 --- 棉花连续 --- czce
# RI0 --- 早籼稻连续 --- czce
# MA0 --- 甲醇连续 --- czce
# FG0 --- 玻璃连续 --- czce
# LR0 --- 晚籼稻连续 --- czce
# SF0 --- 硅铁连续 --- czce
# SM0 --- 锰硅连续 --- czce
# CY0 --- 棉纱连续 --- czce
# AP0 --- 苹果连续 --- czce
# CJ0 --- 红枣连续 --- czce
# UR0 --- 尿素连续 --- czce
# SA0 --- 纯碱连续 --- czce
# PF0 --- 短纤连续 --- czce
# PK0 --- 花生连续 --- czce
# SH0 --- 烧碱连续 --- czce
# PX0 --- 对二甲苯连续 --- czce
# PR0 --- 瓶片连续 --- czce
# PL0 --- 丙烯连续 --- czce
# FU0 --- 燃料油连续 --- shfe
# SC0 --- 上海原油连续 --- ine
# AL0 --- 铝连续 --- shfe
# RU0 --- 天然橡胶连续 --- shfe
# ZN0 --- 沪锌连续 --- shfe
# CU0 --- 铜连续 --- shfe
# AU0 --- 黄金连续 --- shfe
# RB0 --- 螺纹钢连续 --- shfe
# PB0 --- 铅连续 --- shfe
# AG0 --- 白银连续 --- shfe
# BU0 --- 沥青连续 --- shfe
# HC0 --- 热轧卷板连续 --- shfe
# SN0 --- 锡连续 --- shfe
# NI0 --- 镍连续 --- shfe
# SP0 --- 纸浆连续 --- shfe
# NR0 --- 20号胶连续 --- ine
# SS0 --- 不锈钢连续 --- shfe
# LU0 --- 低硫燃料油连续 --- ine
# BC0 --- 国际铜连续 --- ine
# AO0 --- 氧化铝连续 --- shfe
# BR0 --- 丁二烯橡胶连续 --- shfe
# EC0 --- 集运指数欧线期货连续 --- ine
# AD0 --- 铸造铝合金连续 --- shfe
# OP0 --- 胶版印刷纸连续 --- shfe
# IF0 --- 沪深300指数期货连续 --- cffex
# TF0 --- 5年期国债期货连续 --- cffex
# IH0 --- 上证50指数期货连续 --- cffex
# IC0 --- 中证500指数期货连续 --- cffex
# TS0 --- 2年期国债期货连续 --- cffex
# IM0 --- 中证连续指数期货连续 --- cffex
# SI0 --- 工业硅连续 --- gfex
# LC0 --- 碳酸锂连续 --- gfex
# PS0 --- 多晶硅连续 --- gfex
# PT0 --- 铂连续 --- gfex
# PD0 --- 钯连续 --- gfex



# -*- coding: utf-8 -*-
"""
直连 SQLite 的 daily_bar 导入脚本（最简版）
==========================================
流程：先按 contract_code 查 contract 表拿到 contract_id，
      再用 INSERT ... ON CONFLICT DO UPDATE 做 UPSERT。
      SQLite 自动判断是插入还是更新，不做统计。

直接运行: python import_daily_bar.py
"""
import os
import sqlite3
from datetime import date, datetime

# ---- 改成你自己的数据库路径 ----
# DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
DB_PATH = '/Users/lawson/Documents/futures_lab/instance/futures_lab.db'


def _norm_date(d):
    """
    统一成 'YYYY-MM-DD' 字符串。支持：
      - date / datetime / pandas Timestamp 对象
      - 'YYYY-MM-DD' / 'YYYY/MM/DD' / 'YYYY.MM.DD'
      - 'YYYYMMDD'（8 位纯数字字符串或整数）
    解析不了的原样返回。
    """
    if d is None:
        return None

    # date / datetime（pandas.Timestamp 继承自 datetime）
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")

    s = str(d).strip()
    if not s:
        return None

    # 多种格式尝试解析，统一成 YYYY-MM-DD
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 都不匹配，原样返回
    return s


def _parse_float(s):
    if s is None:
        return None
    s = str(s).strip()
    return float(s) if s else None


def _parse_int(s):
    if s is None:
        return None
    s = str(s).strip()
    return int(float(s)) if s else None


def import_daily_bar():
    """
    records: list[dict]，每条格式：
    {
        'contract_code': 'rb2405',
        'trade_date':    '2024-01-15',   # 或 date 对象
        'open': 100.5, 'high': 105.2, 'low': 99.8, 'close': 104.3,
        'settle': 104.0, 'volume': 5000, 'open_interest': 20000,
    }

    返回：成功写入的行数
    """

    records = []
    written = 0


    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        conn.execute("BEGIN")

        # 1) 一次性查出所有涉及的 contract_code -> contract_id
        cur.execute(f"SELECT contract_code, id FROM contract")
        code_to_id = {code: cid for code, cid in cur.fetchall()}

        print(code_to_id)

        for contract_code, id in code_to_id.items():
            futures_zh_daily_sina_df = ak.futures_zh_daily_sina(symbol=contract_code)
            print(futures_zh_daily_sina_df)

            for index, row in futures_zh_daily_sina_df.iterrows():
                da = row['date']
                open = row['open']
                high = row['high']
                low = row['low']
                close = row['close']
                volume = row['volume']
                open_interest = row['hold']
                settle = row['settle']

                data = {'contract_code': contract_code, 'trade_date': da, 'open': open, 'high': high, 'low': low, 'close': close, 'settle': settle, 'volume': volume, 'open_interest': open_interest}
                records.append(data)

            time.sleep(1)


        # 2) UPSERT SQL
        sql = """
            INSERT INTO daily_bar (
                contract_id, trade_date, open, high, low, close,
                settle, volume, open_interest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contract_id, trade_date) DO UPDATE SET
                open          = excluded.open,
                high          = excluded.high,
                low           = excluded.low,
                close         = excluded.close,
                settle        = excluded.settle,
                volume        = excluded.volume,
                open_interest = excluded.open_interest
        """

        # 3) 逐行处理，坏行跳过，不影响其它行
        for r in records:
            try:
                code = (r.get("contract_code") or "").strip()
                cid = code_to_id.get(code)
                if cid is None:
                    print(f"跳过：contract 表中找不到合约 {code!r}")
                    continue

                trade_date = _norm_date(r.get("trade_date"))
                if not trade_date:
                    print(f"跳过：trade_date 不能为空（合约 {code}）")
                    continue

                cur.execute("SAVEPOINT sp")
                try:
                    cur.execute(sql, (
                        cid,
                        trade_date,
                        _parse_float(r.get("open")),
                        _parse_float(r.get("high")),
                        _parse_float(r.get("low")),
                        _parse_float(r.get("close")),
                        _parse_float(r.get("settle")),
                        _parse_int(r.get("volume")),
                        _parse_int(r.get("open_interest")),
                    ))
                    cur.execute("RELEASE SAVEPOINT sp")
                    written += 1
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT sp")
                    raise
            except Exception as exc:
                print(f"跳过一行：{exc}")

        conn.commit()
    finally:
        conn.close()

    return written


def import_basis_bar():

    """
    records: list[dict]，每条格式：
    {
        'contract_code': 'SA2405',
        'trade_date':    '2024-01-15',
        'futures_price': 1639.7,
        'spot_price':    1625.4,
        'basis_value':   -14.3,        # 可为 None，自动算 spot - futures
    }

    返回：成功写入的行数
    """

    records = []
    written = 0


    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        conn.execute("BEGIN")

        # 1) 一次性查出所有涉及的 contract_code -> contract_id
        cur.execute(f"SELECT contract_code, id FROM contract")
        code_to_id = {code: cid for code, cid in cur.fetchall()}

        print(code_to_id)


        today = date.today()                        # 当前日期
        start_day = today - timedelta(days=5)       # 前三天

        start_str = start_day.strftime("%Y%m%d")    # '20260908'
        end_str   = today.strftime("%Y%m%d")        # '20260911'

        for contract_code, id in code_to_id.items():
            symbol = contract_code.rstrip('0') 
            futures_spot_price_daily_df = ak.futures_spot_price_daily(start_day=start_str, end_day=end_str, vars_list=[symbol])
            print(futures_spot_price_daily_df)

            for index, row in futures_spot_price_daily_df.iterrows():
                da = row['date']
                futures_price = row['dominant_contract_price']
                spot_price = row['spot_price']
                basis_value = row['dom_basis']

                data = {'contract_code': contract_code, 'trade_date': da, 'futures_price': futures_price, 'spot_price': spot_price, 'basis_value': basis_value}
                records.append(data)

            time.sleep(1)


        # basis_value 缺失时自动按 futures - spot 计算
        for r in records:
            if r.get("basis_value") in (None, ""):
                fp = _parse_float(r.get("futures_price"))
                sp = _parse_float(r.get("spot_price"))
                if fp is not None and sp is not None:
                    r["basis_value"] = fp - sp


        # 2) UPSERT SQL
        sql = """
            INSERT INTO basis (
                contract_id, trade_date, futures_price, spot_price, basis_value
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(contract_id, trade_date) DO UPDATE SET
                futures_price = excluded.futures_price,
                spot_price    = excluded.spot_price,
                basis_value   = excluded.basis_value
        """

        # 3) 逐行写入
        for r in records:
            try:
                code = (r.get("contract_code") or "").strip()
                cid = code_to_id.get(code)
                if cid is None:
                    print(f"跳过：contract 表中找不到合约 {code!r}")
                    continue

                trade_date = _norm_date(r.get("trade_date"))
                if not trade_date:
                    print(f"跳过：trade_date 不能为空（合约 {code}）")
                    continue

                cur.execute("SAVEPOINT sp")
                try:
                    cur.execute(sql, (
                        cid,
                        trade_date,
                        _parse_float(r.get("futures_price")),
                        _parse_float(r.get("spot_price")),
                        _parse_float(r.get("basis_value")),
                    ))
                    cur.execute("RELEASE SAVEPOINT sp")
                    written += 1
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT sp")
                    raise
            except Exception as exc:
                print(f"跳过一行：{exc}")

        conn.commit()
    finally:
        conn.close()


def import_position_rank():
    """
    records: list[dict]，每条格式：
    {
        'contract_code':      'SA2405',
        'trade_date':         '2024-01-15',
        'total_open_interest': 384201,
        'top5_long_ratio':     23.4,
        'top5_short_ratio':    26.3,
    }
    """

    records = []
    written = 0


    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        conn.execute("BEGIN")

        # 1) 一次性查出所有涉及的 contract_code -> contract_id
        cur.execute(f"SELECT contract_code, id FROM contract")
        code_to_id = {code: cid for code, cid in cur.fetchall()}

        print(code_to_id)


        today = date.today()                        # 当前日期
        start_day = today - timedelta(days=3)       # 前三天

        start_str = start_day.strftime("%Y%m%d")    # '20260908'
        end_str   = today.strftime("%Y%m%d")        # '20260911'

        for contract_code, id in code_to_id.items():
            symbol = contract_code.rstrip('0') 

            try:
                get_rank_sum_daily_df = ak.get_rank_sum_daily(start_day=start_str, end_day=end_str, vars_list=[symbol])
                print(get_rank_sum_daily_df)

                for index, row in get_rank_sum_daily_df.iterrows():
                    sym = row['symbol']
                    if sym == symbol: # 获取全部的
                        da = row['date']
                        top5_long_ratio = row['long_open_interest_top5']
                        top5_short_ratio = row['short_open_interest_top5']
                        total_open_interest = 1

                        data = {'contract_code': contract_code, 'trade_date': da, 'top5_long_ratio': top5_long_ratio, 'top5_short_ratio': top5_short_ratio, 'total_open_interest': total_open_interest}
                        records.append(data)

            except Exception:
                print(f"get_rank_sum_daily error: {symbol}")


            time.sleep(2)


        daily_start_str = _norm_date(start_str)
        daily_end_str = _norm_date(end_str)
        cur.execute(
            f"SELECT contract_id, trade_date, open_interest FROM daily_bar "
            f"WHERE trade_date>='{daily_start_str}' and trade_date<='{daily_end_str}'",
        )

        oi_map = {
            (cid, _norm_date(td)): oi        # ← 统一成字符串
            for cid, td, oi in cur.fetchall()
        }

        print(oi_map)

        for record in records:
            contract_code = record['contract_code']
            cid = code_to_id.get(contract_code)

            trade_date = _norm_date(record['trade_date'])
            top5_long_ratio = record['top5_long_ratio']
            top5_short_ratio = record['top5_short_ratio']

            oi = oi_map.get((cid, trade_date))
            if oi is not None:
                record["total_open_interest"] = oi
                record["top5_long_ratio"] = top5_long_ratio / oi
                record["top5_short_ratio"] = top5_short_ratio / oi


        # 2) UPSERT SQL
        sql = """
            INSERT INTO position_rank (
                contract_id, trade_date, total_open_interest,
                top5_long_ratio, top5_short_ratio
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(contract_id, trade_date) DO UPDATE SET
                total_open_interest = excluded.total_open_interest,
                top5_long_ratio     = excluded.top5_long_ratio,
                top5_short_ratio    = excluded.top5_short_ratio
        """

        # 3) 逐行写入
        for r in records:
            try:
                code = (r.get("contract_code") or "").strip()
                cid = code_to_id.get(code)
                if cid is None:
                    print(f"跳过：contract 表中找不到合约 {code!r}")
                    continue

                trade_date = _norm_date(r.get("trade_date"))
                if not trade_date:
                    print(f"跳过：trade_date 不能为空（合约 {code}）")
                    continue

                cur.execute("SAVEPOINT sp")
                try:
                    cur.execute(sql, (
                        cid,
                        trade_date,
                        _parse_int(r.get("total_open_interest")),
                        _parse_float(r.get("top5_long_ratio")),
                        _parse_float(r.get("top5_short_ratio")),
                    ))
                    cur.execute("RELEASE SAVEPOINT sp")
                    written += 1
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT sp")
                    raise
            except Exception as exc:
                print(f"跳过一行：{exc}")

        conn.commit()
    finally:
        conn.close()

    return written



if __name__ == "__main__":
    # import_daily_bar()
    # import_basis_bar()
    import_position_rank()
