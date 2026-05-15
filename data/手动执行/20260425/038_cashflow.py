"""
接口：cashflow，可以通过数据工具调试和查看数据
描述：获取上市公司现金流量表
限量：用户需要至少2000积分才可以调取；默认优先使用 cashflow_vip 分页批量获取，
      普通 cashflow 作为回退时按多股票批量请求
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=44
本地文档: docs/tushare/tushare.pro/document/29e7f.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          f_ann_date(str,N,实际公告日期), start_date(str,N,公告日开始日期),
          end_date(str,N,公告日结束日期), period(str,N,报告期),
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

同步策略：默认优先 cashflow_vip 按公告日分页增量；失败可回退普通 cashflow 多股票批量
          （ts_code+end_date+report_type 为主键，保留较新的公告/修订记录）
表名：038_cashflow
迁移说明：tushare.fina_cashflow 有数据，字段基本一致，可迁移
用法: python 038_cashflow.py [--start YYYYMMDD] [--end YYYYMMDD]
      [--mode auto|vip|normal] [--page-size 2000] [--batch-size 50]
"""
import argparse, sys
import numpy as np
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


def chunked(items, size):
    if size <= 0:
        raise ValueError("size must be > 0")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def normalize_cashflow_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    for col in COLS:
        if col not in df.columns:
            df[col] = np.nan
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=PK)
    revision_key = None
    for col in ["f_ann_date", "ann_date", "end_date"]:
        if col not in df.columns:
            continue
        revision_key = df[col] if revision_key is None else revision_key.fillna(df[col])
    if revision_key is not None:
        df = df.assign(_revision_key=revision_key)
        df = df.sort_values("_revision_key", na_position="first")
        df = df.drop(columns=["_revision_key"])
    return df.drop_duplicates(subset=PK, keep="last")


def fetch_vip_pages(pro, start_date, end_date, fields, page_size):
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    offset = 0
    while True:
        df = pro.cashflow_vip(
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=offset,
            fields=fields,
        )
        if df is None or df.empty:
            break
        yield df
        if len(df) < page_size:
            break
        offset += page_size


def fetch_normal_batches(pro, codes, start_date, end_date, fields, batch_size):
    for batch in chunked(codes, batch_size):
        df = pro.cashflow(
            ts_code=",".join(batch),
            start_date=start_date,
            end_date=end_date,
            fields=fields,
        )
        yield batch, df


def q_ident(name):
    return '"' + name.replace('"', '""') + '"'


def q_table(table):
    return f"{SCHEMA}.{q_ident(table)}"


def build_latest_upsert_sql(table, cols, pk):
    set_clause = ", ".join(f"{q_ident(c)}=EXCLUDED.{q_ident(c)}" for c in cols if c not in pk)
    pk_clause = ", ".join(q_ident(c) for c in pk)
    col_clause = ",".join(q_ident(c) for c in cols)
    revision_new = 'COALESCE(EXCLUDED."f_ann_date", EXCLUDED."ann_date", EXCLUDED."end_date")'
    revision_old = 'COALESCE(target."f_ann_date", target."ann_date", target."end_date")'
    return f"""
            INSERT INTO {q_table(table)} AS target ({col_clause})
            SELECT {col_clause} FROM {q_table('_tmp_' + table)}
            ON CONFLICT ({pk_clause}) DO UPDATE SET {set_clause}
            WHERE {revision_new} >= {revision_old}
        """


def upsert_latest_df(engine, df, table, cols, pk):
    if df is None or df.empty:
        return 0
    tmp = f"_tmp_{table}"
    with engine.begin() as conn:
        df[cols].to_sql(tmp, conn, schema=SCHEMA, if_exists="replace",
                        index=False, method="multi", chunksize=5000)
        conn.execute(text(build_latest_upsert_sql(table, cols, pk)))
        conn.execute(text(f"DROP TABLE IF EXISTS {q_table(tmp)}"))
    return len(df)


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def get_all_stock_codes(pro):
    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")
    return codes


def sync_by_vip(pro, engine, start, end, page_size):
    print(f"[模式] cashflow_vip 按公告日分页同步 start_date={start}, end_date={end}, page_size={page_size}")
    total_rows, t0 = 0, datetime.now()
    for page_no, df in enumerate(fetch_vip_pages(pro, start, end, FIELDS, page_size), 1):
        df = normalize_cashflow_df(df)
        rows = upsert_latest_df(engine, df, TABLE, COLS, PK)
        total_rows += rows
        elapsed = (datetime.now() - t0).seconds
        print(f"  [VIP第{page_no:03d}页] {rows}条  累计{total_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
    return total_rows


def sync_by_normal_batches(pro, engine, start, end, batch_size):
    print(f"[模式] cashflow 普通接口按股票批量同步 start_date={start}, end_date={end}, batch_size={batch_size}")
    codes = get_all_stock_codes(pro)
    total_rows, t0 = 0, datetime.now()
    total_batches = (len(codes) + batch_size - 1) // batch_size
    for i, (batch, df) in enumerate(fetch_normal_batches(pro, codes, start, end, FIELDS, batch_size), 1):
        df = normalize_cashflow_df(df)
        rows = upsert_latest_df(engine, df, TABLE, COLS, PK)
        total_rows += rows
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 10 == 0:
            print(
                f"  [{i:4d}/{total_batches}] {batch[0]}~{batch[-1]}  "
                f"{rows}条  累计{total_rows}条  {elapsed//60}分{elapsed%60}秒",
                flush=True,
            )
    return total_rows



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--mode", choices=["auto", "vip", "normal"], default="auto",
                        help="auto: 优先 cashflow_vip，失败回退普通批量；vip: 只用 VIP；normal: 只用普通批量")
    parser.add_argument("--page-size", type=int, default=2000,
                        help="cashflow_vip 分页大小")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="普通 cashflow 每次请求拼接的股票数量")
    args = parser.parse_args()
    if args.page_size <= 0:
        parser.error("--page-size 必须大于 0")
    if args.batch_size <= 0:
        parser.error("--batch-size 必须大于 0")

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    if args.mode in ["auto", "vip"]:
        try:
            total_rows = sync_by_vip(pro, engine, start, args.end, args.page_size)
        except Exception as e:
            if args.mode == "vip":
                raise
            print(f"[WARN] cashflow_vip 失败，回退普通批量模式: {e}", flush=True)
            total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)
    else:
        total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
