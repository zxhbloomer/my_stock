"""
接口：balancesheet，可以通过数据工具调试和查看数据
描述：获取上市公司资产负债表
限量：用户需要至少2000积分才可以调取；当前接口只能按单只股票获取其历史数据，
      如需获取某一季度全部上市公司数据，请使用balancesheet_vip接口（需5000积分）
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=36
本地文档: docs/tushare/tushare.pro/document/2a36e.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          start_date(str,N,公告日开始日期), end_date(str,N,公告日结束日期),
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

同步策略：默认优先 balancesheet_vip 按公告日分页增量；失败可回退普通 balancesheet 多股票批量
          （ts_code+end_date+report_type 为主键，保留较新的公告/修订记录）
表名：037_balancesheet
迁移说明：tushare.fina_balancesheet 有数据，字段基本一致，可迁移
用法: python 037_balancesheet.py [--start YYYYMMDD] [--end YYYYMMDD]
      [--mode auto|vip|normal] [--page-size 2000] [--batch-size 50]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "037_balancesheet"
DEFAULT_START = "20100101"

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


def chunked(items, size):
    if size <= 0:
        raise ValueError("size must be > 0")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def normalize_balancesheet_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
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
        df = pro.balancesheet_vip(
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
        df = pro.balancesheet(
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


def sync_by_vip(pro, engine, start, end, page_size):
    print(f"[模式] balancesheet_vip 按公告日分页同步 start_date={start}, end_date={end}, page_size={page_size}")
    total_rows, t0 = 0, datetime.now()
    for page_no, df in enumerate(fetch_vip_pages(pro, start, end, FIELDS, page_size), 1):
        df = normalize_balancesheet_df(df)
        rows = upsert_latest_df(engine, df, TABLE, COLS, PK)
        total_rows += rows
        elapsed = (datetime.now() - t0).seconds
        print(f"  [VIP第{page_no:03d}页] {rows}条  累计{total_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
    return total_rows


def get_all_stock_codes(pro):
    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")
    return codes


def sync_by_normal_batches(pro, engine, start, end, batch_size):
    print(f"[模式] balancesheet 普通接口按股票批量同步 start_date={start}, end_date={end}, batch_size={batch_size}")
    codes = get_all_stock_codes(pro)
    total_rows, t0 = 0, datetime.now()
    total_batches = (len(codes) + batch_size - 1) // batch_size
    for i, (batch, df) in enumerate(fetch_normal_batches(pro, codes, start, end, FIELDS, batch_size), 1):
        df = normalize_balancesheet_df(df)
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
                        help="auto: 优先 balancesheet_vip，失败回退普通批量；vip: 只用 VIP；normal: 只用普通批量")
    parser.add_argument("--page-size", type=int, default=2000,
                        help="balancesheet_vip 分页大小")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="普通 balancesheet 每次请求拼接的股票数量")
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
            print(f"[WARN] balancesheet_vip 失败，回退普通批量模式: {e}", flush=True)
            total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)
    else:
        total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
