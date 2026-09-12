import akshare as ak
import time
from datetime import date, timedelta
import os
import sys
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

        for contract_code, id in code_to_id.items():
            try:
                futures_zh_daily_sina_df = ak.futures_zh_daily_sina(symbol=contract_code)
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

            except Exception:
                print(f"futures_zh_daily_sina error: {contract_code}")


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

        today = date.today()                        # 当前日期
        start_day = today - timedelta(days=5)       # 前三天

        start_str = start_day.strftime("%Y%m%d")    # '20260908'
        end_str   = today.strftime("%Y%m%d")        # '20260911'

        for contract_code, id in code_to_id.items():
            symbol = contract_code.rstrip('0') 

            try:
                futures_spot_price_daily_df = ak.futures_spot_price_daily(start_day=start_str, end_day=end_str, vars_list=[symbol])
                for index, row in futures_spot_price_daily_df.iterrows():
                    da = row['date']
                    futures_price = row['dominant_contract_price']
                    spot_price = row['spot_price']
                    basis_value = row['dom_basis']

                    data = {'contract_code': contract_code, 'trade_date': da, 'futures_price': futures_price, 'spot_price': spot_price, 'basis_value': basis_value}
                    records.append(data)

            except Exception:
                print(f"futures_spot_price_daily error: {symbol}")


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

        today = date.today()                        # 当前日期
        start_day = today - timedelta(days=3)       # 前三天

        start_str = start_day.strftime("%Y%m%d")    # '20260908'
        end_str   = today.strftime("%Y%m%d")        # '20260911'

        for contract_code, id in code_to_id.items():
            symbol = contract_code.rstrip('0') 

            try:
                get_rank_sum_daily_df = ak.get_rank_sum_daily(start_day=start_str, end_day=end_str, vars_list=[symbol])
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
    if len(sys.argv) < 2:
        print("用法: python import_data.py {daily_bar|basis_bar|position_rank}")
        sys.exit(1)

    task = sys.argv[1]

    if task == 'daily_bar':
        import_daily_bar()
    elif task == 'basis_bar':
        import_basis_bar()
    elif task == 'position_rank':
        import_position_rank()
    else:
        print("not support")
