"""
接口：idx_factor_pro，可以通过数据工具调试和查看数据
描述：获取指数每日技术面因子数据，用于跟踪指数当前走势情况，数据由Tushare社区自产，覆盖全历史
      指数包括大盘指数、申万行业指数、中信指数；输出参数_bfq表示不复权
限量：单次最大8000
权限：5000积分每分钟可以请求30次，8000积分以上每分钟500次
接口文档: https://tushare.pro/document/2?doc_id=358
本地文档: docs/tushare/tushare.pro/document/28988.html

输入参数：ts_code(str,N,指数代码), start_date(str,N,开始日期),
          end_date(str,N,结束日期), trade_date(str,N,交易日期)
输出字段：ts_code,trade_date,open,high,low,close,pre_close,change,pct_change,vol,amount,
          asi_bfq,asit_bfq,atr_bfq,bbi_bfq,bias1_bfq,bias2_bfq,bias3_bfq,
          boll_lower_bfq,boll_mid_bfq,boll_upper_bfq,brar_ar_bfq,brar_br_bfq,
          cci_bfq,cr_bfq,dfma_dif_bfq,dfma_difma_bfq,
          dmi_adx_bfq,dmi_adxr_bfq,dmi_mdi_bfq,dmi_pdi_bfq,
          downdays,updays,dpo_bfq,madpo_bfq,
          ema_bfq_10,ema_bfq_20,ema_bfq_250,ema_bfq_30,ema_bfq_5,ema_bfq_60,ema_bfq_90,
          emv_bfq,maemv_bfq,expma_12_bfq,expma_50_bfq,
          kdj_bfq,kdj_d_bfq,kdj_k_bfq,
          ktn_down_bfq,ktn_mid_bfq,ktn_upper_bfq,
          lowdays,topdays,
          macd_bfq,macd_dea_bfq,macd_dif_bfq,
          ma_bfq_10,ma_bfq_20,ma_bfq_250,ma_bfq_30,ma_bfq_5,ma_bfq_60,ma_bfq_90,
          mass_bfq,ma_mass_bfq,mfi_bfq,mtm_bfq,mtmma_bfq,obv_bfq,
          psy_bfq,psyma_bfq,roc_bfq,maroc_bfq,
          rsi_bfq_12,rsi_bfq_24,rsi_bfq_6,
          taq_down_bfq,taq_mid_bfq,taq_up_bfq,
          trix_bfq,trma_bfq,vr_bfq,
          wr_bfq,wr1_bfq,xsii_td1_bfq,xsii_td2_bfq,xsii_td3_bfq,xsii_td4_bfq

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
          注意：只有_bfq（不复权）变体，无_hfq/_qfq
表名：137_idx_factor_pro
迁移说明：tushare schema 中无此表，无需迁移
用法: python 137_idx_factor_pro.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "137_idx_factor_pro"
DEFAULT_START = "19910102"

BASE_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_change,vol,amount"
TECH_FIELDS = ",".join([
    "asi_bfq,asit_bfq,atr_bfq,bbi_bfq",
    "bias1_bfq,bias2_bfq,bias3_bfq",
    "boll_lower_bfq,boll_mid_bfq,boll_upper_bfq",
    "brar_ar_bfq,brar_br_bfq,cci_bfq,cr_bfq",
    "dfma_dif_bfq,dfma_difma_bfq",
    "dmi_adx_bfq,dmi_adxr_bfq,dmi_mdi_bfq,dmi_pdi_bfq",
    "downdays,updays,dpo_bfq,madpo_bfq",
    "ema_bfq_10,ema_bfq_20,ema_bfq_250,ema_bfq_30,ema_bfq_5,ema_bfq_60,ema_bfq_90",
    "emv_bfq,maemv_bfq,expma_12_bfq,expma_50_bfq",
    "kdj_bfq,kdj_d_bfq,kdj_k_bfq",
    "ktn_down_bfq,ktn_mid_bfq,ktn_upper_bfq",
    "lowdays,topdays",
    "macd_bfq,macd_dea_bfq,macd_dif_bfq",
    "ma_bfq_10,ma_bfq_20,ma_bfq_250,ma_bfq_30,ma_bfq_5,ma_bfq_60,ma_bfq_90",
    "mass_bfq,ma_mass_bfq,mfi_bfq,mtm_bfq,mtmma_bfq,obv_bfq",
    "psy_bfq,psyma_bfq,roc_bfq,maroc_bfq",
    "rsi_bfq_12,rsi_bfq_24,rsi_bfq_6",
    "taq_down_bfq,taq_mid_bfq,taq_up_bfq",
    "trix_bfq,trma_bfq,vr_bfq",
    "wr_bfq,wr1_bfq,xsii_td1_bfq,xsii_td2_bfq,xsii_td3_bfq,xsii_td4_bfq",
])

FIELDS = BASE_FIELDS + "," + TECH_FIELDS
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

FLOAT_COLS = [c for c in COLS if c not in ("ts_code", "trade_date")]


def _build_create_sql():
    col_defs = ["    ts_code    VARCHAR(20) NOT NULL",
                "    trade_date DATE        NOT NULL"]
    for c in FLOAT_COLS:
        col_defs.append(f"    {c} FLOAT")
    col_defs.append("    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    col_defs.append(f"    PRIMARY KEY (ts_code, trade_date)")
    cols_sql = ",\n".join(col_defs)
    return f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
{cols_sql}
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

CREATE_SQL = _build_create_sql()


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            df = pro.idx_factor_pro(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception as e:
            print(f"  [SKIP] {d}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 20 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.5)  # 5000积分限速30次/分钟

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
