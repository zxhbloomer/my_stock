"""
接口：balancesheet，可以通过数据工具调试和查看数据
描述：获取上市公司资产负债表
限量：用户需要至少2000积分才可以调取；当前接口只能按单只股票获取其历史数据，
      如需获取某一季度全部上市公司数据，请使用balancesheet_vip接口（需5000积分）
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=36
本地文档: docs/tushare/tushare.pro/document/2a36e.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          start_date(str,N,报告期开始日期), end_date(str,N,报告期结束日期),
          period(str,N,报告期), report_type(str,N,报告类型), comp_type(str,N,公司类型)
输出字段：ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,
          total_share,cap_rese,undistr_porfit,surplus_rese,special_rese,money_cap,
          trad_asset,notes_receiv,accounts_receiv,oth_receiv,prepayment,div_receiv,
          int_receiv,inventories,amor_exp,nca_within_1y,sett_rsrv,loanto_oth_bank_fi,
          premium_receiv,reinsur_receiv,reinsur_res_receiv,pur_resale_fa,
          oth_cur_assets,total_cur_assets,fa_avail_for_sale,htm_invest,lt_eqt_invest,
          invest_real_estate,time_deposits,oth_assets,lt_rec,fix_assets,cip,
          const_materials,fixed_assets_disp,produc_bio_assets,oil_and_gas_assets,
          intan_assets,r_and_d,goodwill,lt_amor_exp,defer_tax_assets,decr_in_disbur,
          oth_nca,total_nca,cash_reser_cb,depos_in_oth_bfi,prec_metals,deriv_assets,
          rr_reins_une_prem,rr_reins_outstd_cla,rr_reins_lins_liab,rr_reins_lthins_liab,
          refund_depos,ph_pledge_loans,refund_cap_depos,indep_acct_assets,client_depos,
          client_prov,transac_seat_fee,invest_as_receiv,total_assets,lt_borr,st_borr,
          cb_borr,depos_ib_deposits,loan_oth_bank,trading_fl,notes_payable,acct_payable,
          adv_receipts,sold_for_repur_fa,comm_payable,payroll_payable,taxes_payable,
          int_payable,div_payable,oth_payable,acc_exp,deferred_inc,st_bonds_payable,
          payable_to_reinsurer,rsrv_insur_cont,acting_trading_sec,acting_uw_sec,
          non_cur_liab_due_1y

同步策略：按股票循环增量（ts_code+end_date+report_type 为主键，upsert）
表名：037_balancesheet
迁移说明：tushare.fina_balancesheet 有数据，字段基本一致，可迁移
用法: python 037_balancesheet.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "037_balancesheet"
DEFAULT_START = "20100101"
LOOKBACK_DAYS = 90

FIELDS = ("ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,"
          "total_share,cap_rese,undistr_porfit,surplus_rese,special_rese,money_cap,"
          "trad_asset,notes_receiv,accounts_receiv,oth_receiv,prepayment,div_receiv,"
          "int_receiv,inventories,amor_exp,nca_within_1y,sett_rsrv,loanto_oth_bank_fi,"
          "premium_receiv,reinsur_receiv,reinsur_res_receiv,pur_resale_fa,"
          "oth_cur_assets,total_cur_assets,fa_avail_for_sale,htm_invest,lt_eqt_invest,"
          "invest_real_estate,time_deposits,oth_assets,lt_rec,fix_assets,cip,"
          "const_materials,fixed_assets_disp,produc_bio_assets,oil_and_gas_assets,"
          "intan_assets,r_and_d,goodwill,lt_amor_exp,defer_tax_assets,decr_in_disbur,"
          "oth_nca,total_nca,cash_reser_cb,depos_in_oth_bfi,prec_metals,deriv_assets,"
          "rr_reins_une_prem,rr_reins_outstd_cla,rr_reins_lins_liab,rr_reins_lthins_liab,"
          "refund_depos,ph_pledge_loans,refund_cap_depos,indep_acct_assets,client_depos,"
          "client_prov,transac_seat_fee,invest_as_receiv,total_assets,lt_borr,st_borr,"
          "cb_borr,depos_ib_deposits,loan_oth_bank,trading_fl,notes_payable,acct_payable,"
          "adv_receipts,sold_for_repur_fa,comm_payable,payroll_payable,taxes_payable,"
          "int_payable,div_payable,oth_payable,acc_exp,deferred_inc,st_bonds_payable,"
          "payable_to_reinsurer,rsrv_insur_cont,acting_trading_sec,acting_uw_sec,"
          "non_cur_liab_due_1y")
COLS = FIELDS.split(",")
PK   = ["ts_code", "end_date", "report_type"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code                VARCHAR(15) NOT NULL,
    ann_date               DATE,
    f_ann_date             DATE,
    end_date               DATE        NOT NULL,
    report_type            VARCHAR(5)  NOT NULL,
    comp_type              VARCHAR(5),
    end_type               VARCHAR(5),
    total_share            FLOAT, cap_rese               FLOAT,
    undistr_porfit         FLOAT, surplus_rese           FLOAT,
    special_rese           FLOAT, money_cap              FLOAT,
    trad_asset             FLOAT, notes_receiv           FLOAT,
    accounts_receiv        FLOAT, oth_receiv             FLOAT,
    prepayment             FLOAT, div_receiv             FLOAT,
    int_receiv             FLOAT, inventories            FLOAT,
    amor_exp               FLOAT, nca_within_1y          FLOAT,
    sett_rsrv              FLOAT, loanto_oth_bank_fi     FLOAT,
    premium_receiv         FLOAT, reinsur_receiv         FLOAT,
    reinsur_res_receiv     FLOAT, pur_resale_fa          FLOAT,
    oth_cur_assets         FLOAT, total_cur_assets       FLOAT,
    fa_avail_for_sale      FLOAT, htm_invest             FLOAT,
    lt_eqt_invest          FLOAT, invest_real_estate     FLOAT,
    time_deposits          FLOAT, oth_assets             FLOAT,
    lt_rec                 FLOAT, fix_assets             FLOAT,
    cip                    FLOAT, const_materials        FLOAT,
    fixed_assets_disp      FLOAT, produc_bio_assets      FLOAT,
    oil_and_gas_assets     FLOAT, intan_assets           FLOAT,
    r_and_d                FLOAT, goodwill               FLOAT,
    lt_amor_exp            FLOAT, defer_tax_assets       FLOAT,
    decr_in_disbur         FLOAT, oth_nca                FLOAT,
    total_nca              FLOAT, cash_reser_cb          FLOAT,
    depos_in_oth_bfi       FLOAT, prec_metals            FLOAT,
    deriv_assets           FLOAT, rr_reins_une_prem      FLOAT,
    rr_reins_outstd_cla    FLOAT, rr_reins_lins_liab     FLOAT,
    rr_reins_lthins_liab   FLOAT, refund_depos           FLOAT,
    ph_pledge_loans        FLOAT, refund_cap_depos       FLOAT,
    indep_acct_assets      FLOAT, client_depos           FLOAT,
    client_prov            FLOAT, transac_seat_fee       FLOAT,
    invest_as_receiv       FLOAT, total_assets           FLOAT,
    lt_borr                FLOAT, st_borr                FLOAT,
    cb_borr                FLOAT, depos_ib_deposits      FLOAT,
    loan_oth_bank          FLOAT, trading_fl             FLOAT,
    notes_payable          FLOAT, acct_payable           FLOAT,
    adv_receipts           FLOAT, sold_for_repur_fa      FLOAT,
    comm_payable           FLOAT, payroll_payable        FLOAT,
    taxes_payable          FLOAT, int_payable            FLOAT,
    div_payable            FLOAT, oth_payable            FLOAT,
    acc_exp                FLOAT, deferred_inc           FLOAT,
    st_bonds_payable       FLOAT, payable_to_reinsurer   FLOAT,
    rsrv_insur_cont        FLOAT, acting_trading_sec     FLOAT,
    acting_uw_sec          FLOAT, non_cur_liab_due_1y    FLOAT,
    update_time            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, end_date, report_type)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_end ON {SCHEMA}."{TABLE}" (end_date);
"""

DATE_COLS  = ["ann_date", "f_ann_date", "end_date"]
FLOAT_COLS = [c for c in COLS if c not in ["ts_code","ann_date","f_ann_date","end_date",
                                             "report_type","comp_type","end_type"]]


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
            df = pro.balancesheet(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
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
