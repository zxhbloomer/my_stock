"""
接口：fina_indicator，可以通过数据工具调试和查看数据
描述：获取上市公司财务指标数据，为避免服务器压力，现阶段每次请求最多返回100条记录，
      可通过设置日期多次请求获取更多数据
限量：单次最多返回100条记录
权限：用户需要至少2000积分才可以调取；如需获取某一季度全部上市公司数据，
      请使用fina_indicator_vip接口（需5000积分）
接口文档: https://tushare.pro/document/2?doc_id=79
本地文档: docs/tushare/tushare.pro/document/2e7c1.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          start_date(str,N,报告期开始日期), end_date(str,N,报告期结束日期),
          period(str,N,报告期)
输出字段：ts_code,ann_date,end_date,eps,dt_eps,total_revenue_ps,revenue_ps,
          capital_rese_ps,surplus_rese_ps,undist_profit_ps,extra_item,profit_dedt,
          gross_margin,current_ratio,quick_ratio,cash_ratio,invturn_days,arturn_days,
          inv_turn,ar_turn,ca_turn,fa_turn,assets_turn,op_income,valuechange_income,
          interst_income,daa,ebit,ebitda,fcff,fcfe,current_exint,noncurrent_exint,
          interestdebt,netdebt,tangible_asset,working_capital,networking_capital,
          invest_capital,retained_earnings,diluted2_eps,bps,ocfps,retainedps,cfps,
          ebit_ps,fcff_ps,fcfe_ps,netprofit_margin,grossprofit_margin,cogs_of_sales,
          expense_of_sales,profit_to_gr,saleexp_to_gr,adminexp_of_gr,finaexp_of_gr,
          impai_ttm,gc_of_gr,op_of_gr,ebit_of_gr,roe,roe_waa,roe_dt,roa,npta,roic,
          roe_yearly,roa2_yearly,roe_avg,opincome_of_ebt,investincome_of_ebt,
          n_op_profit_of_ebt,tax_to_ebt,dtprofit_to_profit,salescash_to_or,ocf_to_or,
          ocf_to_opincome,capitalized_to_da,debt_to_assets,assets_to_eqt,dp_assets_to_eqt,
          ca_to_assets,nca_to_assets,tbassets_to_totalassets,int_to_talcap,
          eqt_to_talcapital,currentdebt_to_debt,longdeb_to_debt,ocf_to_shortdebt,
          debt_to_eqt,eqt_to_debt,eqt_to_interestdebt,tangibleasset_to_debt,
          tangasset_to_intdebt,tangibleasset_to_netdebt,ocf_to_debt,ocf_to_interestdebt,
          ocf_to_netdebt,ebit_to_interest,longdebt_to_workingcapital,ebitda_to_debt,
          turn_days,roa_yearly,roa_dp,fixed_assets,profit_prefin_exp

同步策略：按股票循环增量（ts_code+ann_date+end_date 为主键，upsert）
表名：042_fina_indicator
迁移说明：tushare.fina_indicator 有数据，字段完全一致，可直接迁移
用法: python 042_fina_indicator.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "042_fina_indicator"
DEFAULT_START = "20100101"
LOOKBACK_DAYS = 90

FIELDS = ("ts_code,ann_date,end_date,eps,dt_eps,total_revenue_ps,revenue_ps,"
          "capital_rese_ps,surplus_rese_ps,undist_profit_ps,extra_item,profit_dedt,"
          "gross_margin,current_ratio,quick_ratio,cash_ratio,invturn_days,arturn_days,"
          "inv_turn,ar_turn,ca_turn,fa_turn,assets_turn,op_income,valuechange_income,"
          "interst_income,daa,ebit,ebitda,fcff,fcfe,current_exint,noncurrent_exint,"
          "interestdebt,netdebt,tangible_asset,working_capital,networking_capital,"
          "invest_capital,retained_earnings,diluted2_eps,bps,ocfps,retainedps,cfps,"
          "ebit_ps,fcff_ps,fcfe_ps,netprofit_margin,grossprofit_margin,cogs_of_sales,"
          "expense_of_sales,profit_to_gr,saleexp_to_gr,adminexp_of_gr,finaexp_of_gr,"
          "impai_ttm,gc_of_gr,op_of_gr,ebit_of_gr,roe,roe_waa,roe_dt,roa,npta,roic,"
          "roe_yearly,roa2_yearly,roe_avg,opincome_of_ebt,investincome_of_ebt,"
          "n_op_profit_of_ebt,tax_to_ebt,dtprofit_to_profit,salescash_to_or,ocf_to_or,"
          "ocf_to_opincome,capitalized_to_da,debt_to_assets,assets_to_eqt,dp_assets_to_eqt,"
          "ca_to_assets,nca_to_assets,tbassets_to_totalassets,int_to_talcap,"
          "eqt_to_talcapital,currentdebt_to_debt,longdeb_to_debt,ocf_to_shortdebt,"
          "debt_to_eqt,eqt_to_debt,eqt_to_interestdebt,tangibleasset_to_debt,"
          "tangasset_to_intdebt,tangibleasset_to_netdebt,ocf_to_debt,ocf_to_interestdebt,"
          "ocf_to_netdebt,ebit_to_interest,longdebt_to_workingcapital,ebitda_to_debt,"
          "turn_days,roa_yearly,roa_dp,fixed_assets,profit_prefin_exp")
COLS = FIELDS.split(",")
PK   = ["ts_code", "ann_date", "end_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code                  VARCHAR(15) NOT NULL,
    ann_date                 DATE        NOT NULL,
    end_date                 DATE        NOT NULL,
    eps                      FLOAT, dt_eps                   FLOAT,
    total_revenue_ps         FLOAT, revenue_ps               FLOAT,
    capital_rese_ps          FLOAT, surplus_rese_ps          FLOAT,
    undist_profit_ps         FLOAT, extra_item               FLOAT,
    profit_dedt              FLOAT, gross_margin             FLOAT,
    current_ratio            FLOAT, quick_ratio              FLOAT,
    cash_ratio               FLOAT, invturn_days             FLOAT,
    arturn_days              FLOAT, inv_turn                 FLOAT,
    ar_turn                  FLOAT, ca_turn                  FLOAT,
    fa_turn                  FLOAT, assets_turn              FLOAT,
    op_income                FLOAT, valuechange_income       FLOAT,
    interst_income           FLOAT, daa                      FLOAT,
    ebit                     FLOAT, ebitda                   FLOAT,
    fcff                     FLOAT, fcfe                     FLOAT,
    current_exint            FLOAT, noncurrent_exint         FLOAT,
    interestdebt             FLOAT, netdebt                  FLOAT,
    tangible_asset           FLOAT, working_capital          FLOAT,
    networking_capital       FLOAT, invest_capital           FLOAT,
    retained_earnings        FLOAT, diluted2_eps             FLOAT,
    bps                      FLOAT, ocfps                    FLOAT,
    retainedps               FLOAT, cfps                     FLOAT,
    ebit_ps                  FLOAT, fcff_ps                  FLOAT,
    fcfe_ps                  FLOAT, netprofit_margin         FLOAT,
    grossprofit_margin       FLOAT, cogs_of_sales            FLOAT,
    expense_of_sales         FLOAT, profit_to_gr             FLOAT,
    saleexp_to_gr            FLOAT, adminexp_of_gr           FLOAT,
    finaexp_of_gr            FLOAT, impai_ttm                FLOAT,
    gc_of_gr                 FLOAT, op_of_gr                 FLOAT,
    ebit_of_gr               FLOAT, roe                      FLOAT,
    roe_waa                  FLOAT, roe_dt                   FLOAT,
    roa                      FLOAT, npta                     FLOAT,
    roic                     FLOAT, roe_yearly               FLOAT,
    roa2_yearly              FLOAT, roe_avg                  FLOAT,
    opincome_of_ebt          FLOAT, investincome_of_ebt      FLOAT,
    n_op_profit_of_ebt       FLOAT, tax_to_ebt               FLOAT,
    dtprofit_to_profit       FLOAT, salescash_to_or          FLOAT,
    ocf_to_or                FLOAT, ocf_to_opincome          FLOAT,
    capitalized_to_da        FLOAT, debt_to_assets           FLOAT,
    assets_to_eqt            FLOAT, dp_assets_to_eqt         FLOAT,
    ca_to_assets             FLOAT, nca_to_assets            FLOAT,
    tbassets_to_totalassets  FLOAT, int_to_talcap            FLOAT,
    eqt_to_talcapital        FLOAT, currentdebt_to_debt      FLOAT,
    longdeb_to_debt          FLOAT, ocf_to_shortdebt         FLOAT,
    debt_to_eqt              FLOAT, eqt_to_debt              FLOAT,
    eqt_to_interestdebt      FLOAT, tangibleasset_to_debt    FLOAT,
    tangasset_to_intdebt     FLOAT, tangibleasset_to_netdebt FLOAT,
    ocf_to_debt              FLOAT, ocf_to_interestdebt      FLOAT,
    ocf_to_netdebt           FLOAT, ebit_to_interest         FLOAT,
    longdebt_to_workingcapital FLOAT, ebitda_to_debt         FLOAT,
    turn_days                FLOAT, roa_yearly               FLOAT,
    roa_dp                   FLOAT, fixed_assets             FLOAT,
    profit_prefin_exp        FLOAT,
    update_time              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, ann_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_end ON {SCHEMA}."{TABLE}" (end_date);
"""

DATE_COLS  = ["ann_date", "end_date"]
FLOAT_COLS = [c for c in COLS if c not in ["ts_code", "ann_date", "end_date"]]


def get_start(engine):
    max_d = get_max_date(engine, TABLE, date_col="ann_date")
    if max_d:
        start = (pd.Timestamp(max_d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        print(f"[增量] {TABLE} 最新ann_date={max_d}，从 {start} 开始")
        return start
    return DEFAULT_START


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)

    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")

    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.fina_indicator(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                for col in DATE_COLS:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception as e:
            print(f"  [SKIP] {code}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.2)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
