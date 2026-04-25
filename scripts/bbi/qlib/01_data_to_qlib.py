"""
01_data_to_qlib.py
PostgreSQL(tushare_v2) → Qlib二进制格式（全量覆盖）

用法:
    python scripts/bbi/01_data_to_qlib.py
"""
import struct
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sqlalchemy import create_engine, text
from tqdm import tqdm

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
DB_URL = CFG["database"]["url"]
SCHEMA = CFG["database"]["schema"]
OUTPUT_DIR = Path(CFG["qlib_data"]["output_dir"])
START_DATE = CFG["data"]["start_date"]
END_DATE = CFG["data"]["end_date"]


def get_conn():
    return create_engine(DB_URL).connect()


def write_calendars(conn):
    cal_dir = OUTPUT_DIR / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql(
        text(
            f"SELECT cal_date FROM {SCHEMA}.\"003_trade_cal\" "
            f"WHERE exchange='SSE' AND is_open=1 "
            f"AND cal_date >= '{START_DATE}' AND cal_date <= '{END_DATE}' "
            f"ORDER BY cal_date"
        ),
        conn
    )
    with open(cal_dir / "day.txt", "w") as f:
        for d in df["cal_date"]:
            f.write(str(d)[:10] + "\n")
    print(f"[calendars] {len(df)} trading days written")
    return [str(d)[:10] for d in df["cal_date"]]


def write_instruments(conn):
    inst_dir = OUTPUT_DIR / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql(
        text(
            f"SELECT ts_code, list_date, delist_date FROM {SCHEMA}.\"001_stock_basic\" "
            f"WHERE list_status IN ('L','D') "
            f"AND ts_code NOT LIKE '8%' "
            f"AND name NOT LIKE '%ST%'"
        ),
        conn
    )
    df["delist_date"] = df["delist_date"].fillna("2099-12-31")
    with open(inst_dir / "all.txt", "w") as f:
        for _, row in df.iterrows():
            symbol = row["ts_code"].replace(".", "").lower()
            f.write(f"{symbol}\t{str(row['list_date'])[:10]}\t{str(row['delist_date'])[:10]}\n")
    print(f"[instruments] {len(df)} stocks written")
    return df["ts_code"].tolist()


def write_bin(path: Path, start_idx: int, values: np.ndarray):
    """写Qlib .bin文件：第一个float32是start_index，后续是数据"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        np.hstack([start_idx, values]).astype("<f").tofile(f)


FIELDS_063 = {
    "open":     "open_qfq",
    "high":     "high_qfq",
    "low":      "low_qfq",
    "close":    "close_qfq",
    "volume":   "vol",
    "vwap":     "close_qfq",
    "bbi":      "bbi_qfq",
    "amount":   "amount",
    "turnover": "turnover_rate",
    "pe_ttm":   "pe_ttm",
    "pb":       "pb",
    "circ_mv":  "circ_mv",
}

FIELDS_027 = {}  # 027字段已全部包含在063中，不再单独查询

FIELDS_061 = {
    "winner_rate": "winner_rate",
    "cost_avg":    "weight_avg",
}

FIELDS_080 = {
    "net_mf": "net_mf_amount",
}


def write_stock_features(conn, ts_codes: list, calendar: list):
    feat_dir = OUTPUT_DIR / "features"
    cal_index = {d: i for i, d in enumerate(calendar)}

    print("[features] Loading 063_stk_factor_pro ...")
    df063 = pd.read_sql(
        text(
            f"SELECT ts_code, trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq, "
            f"amount, turnover_rate, pe_ttm, pb, circ_mv "
            f"FROM {SCHEMA}.\"063_stk_factor_pro\" "
            f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
            f"ORDER BY ts_code, trade_date"
        ),
        conn, parse_dates=["trade_date"]
    )

    print("[features] Loading 027_daily_basic ... (skipped, fields merged into 063)")

    print("[features] Loading 061_cyq_perf ...")
    df061 = pd.read_sql(
        text(
            f"SELECT ts_code, trade_date, winner_rate, weight_avg "
            f"FROM {SCHEMA}.\"061_cyq_perf\" "
            f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
            f"ORDER BY ts_code, trade_date"
        ),
        conn, parse_dates=["trade_date"]
    )

    print("[features] Loading 080_moneyflow ...")
    df080 = pd.read_sql(
        text(
            f"SELECT ts_code, trade_date, net_mf_amount "
            f"FROM {SCHEMA}.\"080_moneyflow\" "
            f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
            f"ORDER BY ts_code, trade_date"
        ),
        conn, parse_dates=["trade_date"]
    )

    cal_dt = pd.to_datetime(calendar)

    # 建立索引加速查找
    df063 = df063.set_index(["ts_code", "trade_date"])
    df061 = df061.set_index(["ts_code", "trade_date"])
    df080 = df080.set_index(["ts_code", "trade_date"])

    for ts_code in tqdm(ts_codes, desc="Writing features"):
        symbol = ts_code.replace(".", "").lower()
        stock_dir = feat_dir / symbol

        def get_series(df, col):
            try:
                s = df.loc[ts_code][col]
                s.index = pd.to_datetime(s.index)
                return s.reindex(cal_dt).values
            except KeyError:
                return np.full(len(cal_dt), np.nan)

        start_idx = 0

        for qlib_name, col in FIELDS_063.items():
            write_bin(stock_dir / f"{qlib_name}.day.bin", start_idx, get_series(df063, col))

        write_bin(stock_dir / "factor.day.bin", start_idx, np.ones(len(cal_dt), dtype=np.float32))

        for qlib_name, col in FIELDS_061.items():
            write_bin(stock_dir / f"{qlib_name}.day.bin", start_idx, get_series(df061, col))

        for qlib_name, col in FIELDS_080.items():
            write_bin(stock_dir / f"{qlib_name}.day.bin", start_idx, get_series(df080, col))


def main():
    print(f"[01_data_to_qlib] output={OUTPUT_DIR}")
    conn = get_conn()
    try:
        calendar = write_calendars(conn)
        ts_codes = write_instruments(conn)
        write_stock_features(conn, ts_codes, calendar)
        print("[01_data_to_qlib] Done!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
