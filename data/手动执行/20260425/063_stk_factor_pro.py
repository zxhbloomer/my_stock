"""
接口：stk_factor_pro，可以通过数据工具调试和查看数据
描述：获取股票每日技术面因子数据，用于跟踪股票当前走势情况，数据由Tushare社区自产，
      覆盖全历史；_bfq表示不复权，_qfq表示前复权，_hfq表示后复权
限量：单次调取最多返回10000条数据，可以通过日期参数循环
权限：5000积分每分钟可以请求30次，8000积分以上每分钟500次
接口文档: https://tushare.pro/document/2?doc_id=328
本地文档: docs/tushare/tushare.pro/document/23ac1.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,open,open_hfq,open_qfq,high,high_hfq,high_qfq,
          low,low_hfq,low_qfq,close,close_hfq,close_qfq,pre_close,change,pct_chg,
          vol,amount,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,
          ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,
          circ_mv,adj_factor,
          asi_bfq,asi_hfq,asi_qfq,asit_bfq,asit_hfq,asit_qfq,
          atr_bfq,atr_hfq,atr_qfq,bbi_bfq,bbi_hfq,bbi_qfq,
          bias1_bfq,bias1_hfq,bias1_qfq,bias2_bfq,bias2_hfq,bias2_qfq,
          bias3_bfq,bias3_hfq,bias3_qfq,
          boll_lower_bfq,boll_lower_hfq,boll_lower_qfq,
          boll_mid_bfq,boll_mid_hfq,boll_mid_qfq,
          boll_upper_bfq,boll_upper_hfq,boll_upper_qfq,
          brar_ar_bfq,brar_ar_hfq,brar_ar_qfq,brar_br_bfq,brar_br_hfq,brar_br_qfq,
          cci_bfq,cci_hfq,cci_qfq,cr_bfq,cr_hfq,cr_qfq,
          dfma_dif_bfq,dfma_dif_hfq,dfma_dif_qfq,
          dfma_difma_bfq,dfma_difma_hfq,dfma_difma_qfq,
          dmi_adx_bfq,dmi_adx_hfq,dmi_adx_qfq,dmi_adxr_bfq,dmi_adxr_hfq,dmi_adxr_qfq,
          dmi_mdi_bfq,dmi_mdi_hfq,dmi_mdi_qfq,dmi_pdi_bfq,dmi_pdi_hfq,dmi_pdi_qfq,
          downdays,updays,
          dpo_bfq,dpo_hfq,dpo_qfq,madpo_bfq,madpo_hfq,madpo_qfq,
          ema_bfq_10,ema_hfq_10,ema_qfq_10,ema_bfq_20,ema_hfq_20,ema_qfq_20,
          ema_bfq_250,ema_hfq_250,ema_qfq_250,ema_bfq_30,ema_hfq_30,ema_qfq_30,
          ema_bfq_5,ema_hfq_5,ema_qfq_5,ema_bfq_60,ema_hfq_60,ema_qfq_60,
          ema_bfq_90,ema_hfq_90,ema_qfq_90,
          emv_bfq,emv_hfq,emv_qfq,maemv_bfq,maemv_hfq,maemv_qfq,
          expma_12_bfq,expma_12_hfq,expma_12_qfq,expma_50_bfq,expma_50_hfq,expma_50_qfq,
          kdj_bfq,kdj_hfq,kdj_qfq,kdj_d_bfq,kdj_d_hfq,kdj_d_qfq,
          kdj_k_bfq,kdj_k_hfq,kdj_k_qfq,
          ktn_down_bfq,ktn_down_hfq,ktn_down_qfq,
          ktn_mid_bfq,ktn_mid_hfq,ktn_mid_qfq,
          ktn_upper_bfq,ktn_upper_hfq,ktn_upper_qfq,
          lowdays,topdays,
          macd_bfq,macd_hfq,macd_qfq,macd_dea_bfq,macd_dea_hfq,macd_dea_qfq,
          macd_dif_bfq,macd_dif_hfq,macd_dif_qfq,
          ma_bfq_10,ma_hfq_10,ma_qfq_10,ma_bfq_20,ma_hfq_20,ma_qfq_20,
          ma_bfq_250,ma_hfq_250,ma_qfq_250,ma_bfq_30,ma_hfq_30,ma_qfq_30,
          ma_bfq_5,ma_hfq_5,ma_qfq_5,ma_bfq_60,ma_hfq_60,ma_qfq_60,
          ma_bfq_90,ma_hfq_90,ma_qfq_90,
          mass_bfq,mass_hfq,mass_qfq,ma_mass_bfq,ma_mass_hfq,ma_mass_qfq,
          mfi_bfq,mfi_hfq,mfi_qfq,
          mtm_bfq,mtm_hfq,mtm_qfq,mtmma_bfq,mtmma_hfq,mtmma_qfq,
          obv_bfq,obv_hfq,obv_qfq,
          psy_bfq,psy_hfq,psy_qfq,psyma_bfq,psyma_hfq,psyma_qfq,
          roc_bfq,roc_hfq,roc_qfq,maroc_bfq,maroc_hfq,maroc_qfq,
          rsi_bfq_12,rsi_hfq_12,rsi_qfq_12,rsi_bfq_24,rsi_hfq_24,rsi_qfq_24,
          rsi_bfq_6,rsi_hfq_6,rsi_qfq_6,
          taq_down_bfq,taq_down_hfq,taq_down_qfq,
          taq_mid_bfq,taq_mid_hfq,taq_mid_qfq,
          taq_up_bfq,taq_up_hfq,taq_up_qfq,
          trix_bfq,trix_hfq,trix_qfq,trma_bfq,trma_hfq,trma_qfq,
          vr_bfq,vr_hfq,vr_qfq,
          wr_bfq,wr_hfq,wr_qfq,wr1_bfq,wr1_hfq,wr1_qfq,
          xsii_td1_bfq,xsii_td1_hfq,xsii_td1_qfq,
          xsii_td2_bfq,xsii_td2_hfq,xsii_td2_qfq,
          xsii_td3_bfq,xsii_td3_hfq,xsii_td3_qfq,
          xsii_td4_bfq,xsii_td4_hfq,xsii_td4_qfq

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
          注意：字段极多（200+），单次最多10000行，按日期循环效率最高
表名：063_stk_factor_pro
迁移说明：tushare schema 中无此表，无需迁移
用法: python 063_stk_factor_pro.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "063_stk_factor_pro"
DEFAULT_START = "20100104"
# 基础行情字段
BASE_FIELDS = "ts_code,trade_date,open,open_hfq,open_qfq,high,high_hfq,high_qfq,low,low_hfq,low_qfq,close,close_hfq,close_qfq,pre_close,change,pct_chg,vol,amount,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv,adj_factor"

# 技术指标字段（三个复权版本）
TECH_FIELDS = ",".join([
    "asi_bfq,asi_hfq,asi_qfq,asit_bfq,asit_hfq,asit_qfq",
    "atr_bfq,atr_hfq,atr_qfq,bbi_bfq,bbi_hfq,bbi_qfq",
    "bias1_bfq,bias1_hfq,bias1_qfq,bias2_bfq,bias2_hfq,bias2_qfq,bias3_bfq,bias3_hfq,bias3_qfq",
    "boll_lower_bfq,boll_lower_hfq,boll_lower_qfq,boll_mid_bfq,boll_mid_hfq,boll_mid_qfq,boll_upper_bfq,boll_upper_hfq,boll_upper_qfq",
    "brar_ar_bfq,brar_ar_hfq,brar_ar_qfq,brar_br_bfq,brar_br_hfq,brar_br_qfq",
    "cci_bfq,cci_hfq,cci_qfq,cr_bfq,cr_hfq,cr_qfq",
    "dfma_dif_bfq,dfma_dif_hfq,dfma_dif_qfq,dfma_difma_bfq,dfma_difma_hfq,dfma_difma_qfq",
    "dmi_adx_bfq,dmi_adx_hfq,dmi_adx_qfq,dmi_adxr_bfq,dmi_adxr_hfq,dmi_adxr_qfq,dmi_mdi_bfq,dmi_mdi_hfq,dmi_mdi_qfq,dmi_pdi_bfq,dmi_pdi_hfq,dmi_pdi_qfq",
    "downdays,updays",
    "dpo_bfq,dpo_hfq,dpo_qfq,madpo_bfq,madpo_hfq,madpo_qfq",
    "ema_bfq_10,ema_hfq_10,ema_qfq_10,ema_bfq_20,ema_hfq_20,ema_qfq_20,ema_bfq_250,ema_hfq_250,ema_qfq_250,ema_bfq_30,ema_hfq_30,ema_qfq_30,ema_bfq_5,ema_hfq_5,ema_qfq_5,ema_bfq_60,ema_hfq_60,ema_qfq_60,ema_bfq_90,ema_hfq_90,ema_qfq_90",
    "emv_bfq,emv_hfq,emv_qfq,maemv_bfq,maemv_hfq,maemv_qfq",
    "expma_12_bfq,expma_12_hfq,expma_12_qfq,expma_50_bfq,expma_50_hfq,expma_50_qfq",
    "kdj_bfq,kdj_hfq,kdj_qfq,kdj_d_bfq,kdj_d_hfq,kdj_d_qfq,kdj_k_bfq,kdj_k_hfq,kdj_k_qfq",
    "ktn_down_bfq,ktn_down_hfq,ktn_down_qfq,ktn_mid_bfq,ktn_mid_hfq,ktn_mid_qfq,ktn_upper_bfq,ktn_upper_hfq,ktn_upper_qfq",
    "lowdays,topdays",
    "macd_bfq,macd_hfq,macd_qfq,macd_dea_bfq,macd_dea_hfq,macd_dea_qfq,macd_dif_bfq,macd_dif_hfq,macd_dif_qfq",
    "ma_bfq_10,ma_hfq_10,ma_qfq_10,ma_bfq_20,ma_hfq_20,ma_qfq_20,ma_bfq_250,ma_hfq_250,ma_qfq_250,ma_bfq_30,ma_hfq_30,ma_qfq_30,ma_bfq_5,ma_hfq_5,ma_qfq_5,ma_bfq_60,ma_hfq_60,ma_qfq_60,ma_bfq_90,ma_hfq_90,ma_qfq_90",
    "mass_bfq,mass_hfq,mass_qfq,ma_mass_bfq,ma_mass_hfq,ma_mass_qfq",
    "mfi_bfq,mfi_hfq,mfi_qfq",
    "mtm_bfq,mtm_hfq,mtm_qfq,mtmma_bfq,mtmma_hfq,mtmma_qfq",
    "obv_bfq,obv_hfq,obv_qfq",
    "psy_bfq,psy_hfq,psy_qfq,psyma_bfq,psyma_hfq,psyma_qfq",
    "roc_bfq,roc_hfq,roc_qfq,maroc_bfq,maroc_hfq,maroc_qfq",
    "rsi_bfq_12,rsi_hfq_12,rsi_qfq_12,rsi_bfq_24,rsi_hfq_24,rsi_qfq_24,rsi_bfq_6,rsi_hfq_6,rsi_qfq_6",
    "taq_down_bfq,taq_down_hfq,taq_down_qfq,taq_mid_bfq,taq_mid_hfq,taq_mid_qfq,taq_up_bfq,taq_up_hfq,taq_up_qfq",
    "trix_bfq,trix_hfq,trix_qfq,trma_bfq,trma_hfq,trma_qfq",
    "vr_bfq,vr_hfq,vr_qfq",
    "wr_bfq,wr_hfq,wr_qfq,wr1_bfq,wr1_hfq,wr1_qfq",
    "xsii_td1_bfq,xsii_td1_hfq,xsii_td1_qfq,xsii_td2_bfq,xsii_td2_hfq,xsii_td2_qfq,xsii_td3_bfq,xsii_td3_hfq,xsii_td3_qfq,xsii_td4_bfq,xsii_td4_hfq,xsii_td4_qfq",
])

FIELDS = BASE_FIELDS + "," + TECH_FIELDS
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

# 拆分字段为两批，避免单次响应体过大（>1MB）导致 JSON 截断
_all_cols = COLS[:]
_mid      = len(_all_cols) // 2
FIELDS_A  = ",".join(_all_cols[:_mid])   # 前半段（含 ts_code/trade_date）
FIELDS_B  = "ts_code,trade_date," + ",".join(_all_cols[_mid:])  # 后半段（带 PK 用于 merge）

# 所有字段均为FLOAT，除ts_code/trade_date外
FLOAT_COLS = [c for c in COLS if c not in ("ts_code", "trade_date")]

# 动态生成建表SQL（字段太多，逐一列出）
def _build_create_sql():
    col_defs = ["    ts_code    VARCHAR(15) NOT NULL",
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
            # 分两批请求，避免单次 JSON 响应体超过 1MB 导致截断
            df_a = pro.stk_factor_pro(trade_date=d, fields=FIELDS_A)
            df_b = pro.stk_factor_pro(trade_date=d, fields=FIELDS_B)
            if df_a is not None and not df_a.empty and df_b is not None and not df_b.empty:
                df = pd.merge(df_a, df_b, on=PK, how="inner")
            else:
                df = pd.DataFrame()
            if not df.empty:
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
