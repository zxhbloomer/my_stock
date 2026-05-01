"""
接口：cashflow，可以通过数据工具调试和查看数据
描述：获取上市公司现金流量表
限量：用户需要至少2000积分才可以调取；当前接口只能按单只股票获取其历史数据，
      如需获取某一季度全部上市公司数据，请使用cashflow_vip接口（需5000积分）
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=44
本地文档: docs/tushare/tushare.pro/document/29e7f.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          f_ann_date(str,N,实际公告日期), start_date(str,N,报告期开始日期),
          end_date(str,N,报告期结束日期), period(str,N,报告期),
          report_type(str,N,报告类型), comp_type(str,N,公司类型), is_calc(int,N,是否计算值)
输出字段：ts_code,ann_date,f_ann_date,end_date,comp_type,report_type,end_type,
          net_profit,finan_exp,c_fr_sale_sg,recp_tax_rends,n_depos_incr_fi,
          n_incr_loans_cb,n_inc_borr_oth_fi,prem_fr_orig_contr,n_incr_insured_dep,
          n_reinsur_prem,n_incr_disp_tfa,ifc_cash_incr,n_incr_disp_faas,
          n_incr_loans_oth_bank,n_cap_incr_repur,c_fr_oth_operate_a,c_inf_fr_operate_a,
          c_paid_goods_s,c_paid_to_for_empl,c_paid_for_taxes,n_incr_clt_loan_adv,
          n_incr_dep_cbob,c_pay_claims_orig_inco,pay_handling_chrg,pay_comm_insur_plcy,
          oth_cash_pay_oper_act,st_cash_out_act,n_cashflow_act,oth_recp_ral_inv_act,
          c_disp_withdrwl_invest,c_recp_return_invest,n_recp_disp_fiolta,n_recp_disp_sobu,
          stot_inflows_inv_act,c_pay_acq_const_fiolta,c_paid_invest,n_disp_subs_oth_biz,
          oth_pay_ral_inv_act,n_incr_pledge_loan,stot_out_inv_act,n_cashflow_inv_act,
          c_recp_borrow,proc_issue_bonds,oth_cash_recp_ral_fnc_act,stot_cash_in_fnc_act,
          free_cashflow,c_prepay_amt_borr,c_pay_dist_dpcp_int_exp,
          incl_dvd_profit_paid_sc_ms,oth_cashpay_ral_fnc_act,stot_cashout_fnc_act,
          n_cash_flows_fnc_act,eff_fx_flu_cash,n_incr_cash_cash_equ,
          c_cash_equ_beg_period,c_cash_equ_end_period,c_recp_cap_contrib,
          incl_cash_rec_saims,uncon_invest_loss,prov_depr_assets,depr_fa_coga_dpba,
          amort_intang_assets,lt_amort_deferred_exp,decr_deferred_exp,incr_acc_exp,
          loss_disp_fiolta,loss_scr_fa,loss_fv_chg,invest_loss,decr_def_inc_tax_assets,
          incr_def_inc_tax_liab,decr_inventories,decr_oper_payable,incr_oper_payable,
          others,im_net_cashflow_oper_act,conv_debt_into_cap,conv_copbonds_due_within_1y,
          fa_fnc_leases,im_n_incr_cash_equ,net_dism_capital_add,net_cash_rece_sec,
          credit_impa_loss,use_right_asset_dep

同步策略：按股票循环增量（ts_code+end_date+report_type 为主键，upsert）
表名：038_cashflow
迁移说明：tushare.fina_cashflow 有数据，字段基本一致，可迁移
用法: python 038_cashflow.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "038_cashflow"
DEFAULT_START = "20100101"

FIELDS = ("ts_code,ann_date,f_ann_date,end_date,comp_type,report_type,end_type,"
          "net_profit,finan_exp,c_fr_sale_sg,recp_tax_rends,n_depos_incr_fi,"
          "n_incr_loans_cb,n_inc_borr_oth_fi,prem_fr_orig_contr,n_incr_insured_dep,"
          "n_reinsur_prem,n_incr_disp_tfa,ifc_cash_incr,n_incr_disp_faas,"
          "n_incr_loans_oth_bank,n_cap_incr_repur,c_fr_oth_operate_a,c_inf_fr_operate_a,"
          "c_paid_goods_s,c_paid_to_for_empl,c_paid_for_taxes,n_incr_clt_loan_adv,"
          "n_incr_dep_cbob,c_pay_claims_orig_inco,pay_handling_chrg,pay_comm_insur_plcy,"
          "oth_cash_pay_oper_act,st_cash_out_act,n_cashflow_act,oth_recp_ral_inv_act,"
          "c_disp_withdrwl_invest,c_recp_return_invest,n_recp_disp_fiolta,n_recp_disp_sobu,"
          "stot_inflows_inv_act,c_pay_acq_const_fiolta,c_paid_invest,n_disp_subs_oth_biz,"
          "oth_pay_ral_inv_act,n_incr_pledge_loan,stot_out_inv_act,n_cashflow_inv_act,"
          "c_recp_borrow,proc_issue_bonds,oth_cash_recp_ral_fnc_act,stot_cash_in_fnc_act,"
          "free_cashflow,c_prepay_amt_borr,c_pay_dist_dpcp_int_exp,"
          "incl_dvd_profit_paid_sc_ms,oth_cashpay_ral_fnc_act,stot_cashout_fnc_act,"
          "n_cash_flows_fnc_act,eff_fx_flu_cash,n_incr_cash_cash_equ,"
          "c_cash_equ_beg_period,c_cash_equ_end_period,c_recp_cap_contrib,"
          "incl_cash_rec_saims,uncon_invest_loss,prov_depr_assets,depr_fa_coga_dpba,"
          "amort_intang_assets,lt_amort_deferred_exp,decr_deferred_exp,incr_acc_exp,"
          "loss_disp_fiolta,loss_scr_fa,loss_fv_chg,invest_loss,decr_def_inc_tax_assets,"
          "incr_def_inc_tax_liab,decr_inventories,decr_oper_payable,incr_oper_payable,"
          "others,im_net_cashflow_oper_act,conv_debt_into_cap,conv_copbonds_due_within_1y,"
          "fa_fnc_leases,im_n_incr_cash_equ,net_dism_capital_add,net_cash_rece_sec,"
          "credit_impa_loss,use_right_asset_dep")
COLS = FIELDS.split(",")
PK   = ["ts_code", "end_date", "report_type"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code                    VARCHAR(15) NOT NULL,
    ann_date                   DATE,
    f_ann_date                 DATE,
    end_date                   DATE        NOT NULL,
    comp_type                  VARCHAR(5),
    report_type                VARCHAR(5)  NOT NULL,
    end_type                   VARCHAR(5),
    net_profit                 FLOAT, finan_exp                  FLOAT,
    c_fr_sale_sg               FLOAT, recp_tax_rends             FLOAT,
    n_depos_incr_fi            FLOAT, n_incr_loans_cb            FLOAT,
    n_inc_borr_oth_fi          FLOAT, prem_fr_orig_contr         FLOAT,
    n_incr_insured_dep         FLOAT, n_reinsur_prem             FLOAT,
    n_incr_disp_tfa            FLOAT, ifc_cash_incr              FLOAT,
    n_incr_disp_faas           FLOAT, n_incr_loans_oth_bank      FLOAT,
    n_cap_incr_repur           FLOAT, c_fr_oth_operate_a         FLOAT,
    c_inf_fr_operate_a         FLOAT, c_paid_goods_s             FLOAT,
    c_paid_to_for_empl         FLOAT, c_paid_for_taxes           FLOAT,
    n_incr_clt_loan_adv        FLOAT, n_incr_dep_cbob            FLOAT,
    c_pay_claims_orig_inco     FLOAT, pay_handling_chrg          FLOAT,
    pay_comm_insur_plcy        FLOAT, oth_cash_pay_oper_act      FLOAT,
    st_cash_out_act            FLOAT, n_cashflow_act             FLOAT,
    oth_recp_ral_inv_act       FLOAT, c_disp_withdrwl_invest     FLOAT,
    c_recp_return_invest       FLOAT, n_recp_disp_fiolta         FLOAT,
    n_recp_disp_sobu           FLOAT, stot_inflows_inv_act       FLOAT,
    c_pay_acq_const_fiolta     FLOAT, c_paid_invest              FLOAT,
    n_disp_subs_oth_biz        FLOAT, oth_pay_ral_inv_act        FLOAT,
    n_incr_pledge_loan         FLOAT, stot_out_inv_act           FLOAT,
    n_cashflow_inv_act         FLOAT, c_recp_borrow              FLOAT,
    proc_issue_bonds           FLOAT, oth_cash_recp_ral_fnc_act  FLOAT,
    stot_cash_in_fnc_act       FLOAT, free_cashflow              FLOAT,
    c_prepay_amt_borr          FLOAT, c_pay_dist_dpcp_int_exp    FLOAT,
    incl_dvd_profit_paid_sc_ms FLOAT, oth_cashpay_ral_fnc_act    FLOAT,
    stot_cashout_fnc_act       FLOAT, n_cash_flows_fnc_act       FLOAT,
    eff_fx_flu_cash            FLOAT, n_incr_cash_cash_equ       FLOAT,
    c_cash_equ_beg_period      FLOAT, c_cash_equ_end_period      FLOAT,
    c_recp_cap_contrib         FLOAT, incl_cash_rec_saims        FLOAT,
    uncon_invest_loss          FLOAT, prov_depr_assets           FLOAT,
    depr_fa_coga_dpba          FLOAT, amort_intang_assets        FLOAT,
    lt_amort_deferred_exp      FLOAT, decr_deferred_exp          FLOAT,
    incr_acc_exp               FLOAT, loss_disp_fiolta           FLOAT,
    loss_scr_fa                FLOAT, loss_fv_chg                FLOAT,
    invest_loss                FLOAT, decr_def_inc_tax_assets    FLOAT,
    incr_def_inc_tax_liab      FLOAT, decr_inventories           FLOAT,
    decr_oper_payable          FLOAT, incr_oper_payable          FLOAT,
    others                     FLOAT, im_net_cashflow_oper_act   FLOAT,
    conv_debt_into_cap         FLOAT, conv_copbonds_due_within_1y FLOAT,
    fa_fnc_leases              FLOAT, im_n_incr_cash_equ         FLOAT,
    net_dism_capital_add       FLOAT, net_cash_rece_sec          FLOAT,
    credit_impa_loss           FLOAT, use_right_asset_dep        FLOAT,
    update_time                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, end_date, report_type)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_end ON {SCHEMA}."{TABLE}" (end_date);
"""

DATE_COLS  = ["ann_date", "f_ann_date", "end_date"]
FLOAT_COLS = [c for c in COLS if c not in ["ts_code","ann_date","f_ann_date","end_date",
                                             "comp_type","report_type","end_type"]]


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

    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.cashflow(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
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

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
