"""
接口：ths_member，可以通过数据工具调试和查看数据
描述：获取同花顺概念板块成分列表
限量：每分钟可调取200次，可按概念板块代码循环提取所有成分
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=261
本地文档: docs/tushare/tushare.pro/document/206ba.html

同步策略：静态全量，先获取同花顺板块代码，再按板块代码循环拉取成分（全删全插）
表名：096_ths_member
用法: python 096_ths_member.py
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "096_ths_member"
FIELDS = "ts_code,con_code,con_name,weight,in_date,out_date,is_new"
COLS   = FIELDS.split(",") + ["is_new_key"]
PK     = ["ts_code", "con_code", "is_new_key"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(15) NOT NULL,
    con_code    VARCHAR(15) NOT NULL,
    con_name    VARCHAR(80),
    weight      FLOAT,
    in_date     DATE,
    out_date    DATE,
    is_new      VARCHAR(5),
    is_new_key  VARCHAR(5)  NOT NULL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, con_code, is_new_key)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_con ON {SCHEMA}."{TABLE}" (con_code);
"""


def fetch_index_codes(pro):
    df = pro.ths_index(fields="ts_code")
    if df is None or df.empty or "ts_code" not in df.columns:
        raise RuntimeError("ths_index 返回异常，未获取到任何板块代码")
    return sorted(df["ts_code"].dropna().astype(str).unique().tolist())


def fetch_members_by_index(pro, codes):
    frames = []
    t0 = datetime.now()
    for i, code in enumerate(codes, 1):
        df = pro.ths_member(ts_code=code, fields=FIELDS)
        if df is None or df.empty:
            rows = 0
        else:
            frames.append(df)
            rows = len(df)
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
    if not frames:
        return pd.DataFrame(columns=FIELDS.split(","))
    return pd.concat(frames, ignore_index=True)


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ing")
    codes = fetch_index_codes(pro)
    print(f"共 {len(codes)} 个同花顺板块")
    df = fetch_members_by_index(pro, codes)
    if df is not None and not df.empty:
        df["in_date"] = pd.to_datetime(df["in_date"], errors="coerce")
        df["out_date"] = pd.to_datetime(df["out_date"], errors="coerce")
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
        df["is_new_key"] = df["is_new"].fillna("").astype(str)
        df = df.dropna(subset=["ts_code", "con_code"]).drop_duplicates(subset=PK)
        rows = truncate_and_insert(engine, df, TABLE, COLS)
    else:
        rows = 0
    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ok")
    print(f"\n[完成] 全量插入 {rows:,} 条")


if __name__ == "__main__":
    main()
