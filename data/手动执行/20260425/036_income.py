"""
接口：income，可以通过数据工具调试和查看数据
描述：获取上市公司财务利润表数据
限量：用户需要至少2000积分才可以调取；默认优先使用 income_vip 分页批量获取，
      普通 income 作为回退时按多股票批量请求
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=33
本地文档: docs/tushare/tushare.pro/document/28b70.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          f_ann_date(str,N,实际公告日期), start_date(str,N,公告日开始日期),
          end_date(str,N,公告日结束日期), period(str,N,报告期),
          report_type(str,N,报告类型), comp_type(str,N,公司类型)
输出字段：ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,
          basic_eps,diluted_eps,total_revenue,revenue,int_income,prem_earned,
          comm_income,n_commis_income,n_oth_income,n_oth_b_income,prem_income,
          out_prem,une_prem_reser,reins_income,n_sec_tb_income,n_sec_uw_income,
          n_asset_mg_income,oth_b_income,fv_value_chg_gain,invest_income,
          ass_invest_income,forex_gain,total_cogs,oper_cost,int_exp,comm_exp,
          biz_tax_surchg,sell_exp,admin_exp,fin_exp,assets_impair_loss,
          prem_refund,compens_payout,reser_insur_liab,div_payt,reins_exp,
          oper_exp,compens_payout_refu,insur_reser_refu,reins_cost_refund,
          other_bus_cost,operate_profit,non_oper_income,non_oper_exp,
          nca_disploss,total_profit,income_tax,n_income,n_income_attr_p,
          minority_gain,oth_compr_income,t_compr_income,compr_inc_attr_p,
          compr_inc_attr_m_s,ebit,ebitda,insurance_exp,undist_profit,
          distable_profit,rd_exp,fin_exp_int_exp,fin_exp_int_inc,
          transfer_surplus_rese,transfer_housing_imprest,transfer_oth,
          adj_lossgain,withdra_legal_surplus,withdra_legal_pubfund,
          withdra_biz_devfund,withdra_rese_fund,withdra_oth_ersu,
          workers_welfare,distr_profit_shrhder,prfshare_payable_dvd,
          comshare_payable_dvd,capit_comstock_div,net_after_nr_lp_correct,
          credit_impa_loss,net_expo_hedging_benefits,oth_impair_loss_assets,
          total_opcost,amodcost_fin_assets,oth_income,asset_disp_income,
          continued_net_profit

同步策略：默认优先 income_vip 按公告日分页增量；失败可回退普通 income 多股票批量
          （ts_code+end_date+report_type 为主键，保留较新的公告/修订记录）
表名：036_income
迁移说明：tushare.fina_income 有数据，字段基本一致（缺少end_type字段），可迁移
用法: python 036_income.py [--start YYYYMMDD] [--end YYYYMMDD]
      [--mode auto|vip|normal] [--page-size 2000] [--batch-size 50]
"""
import argparse, sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "036_income"
DEFAULT_START = "20100101"

FIELDS = ("ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,"
          "basic_eps,diluted_eps,total_revenue,revenue,int_income,prem_earned,"
          "comm_income,n_commis_income,n_oth_income,n_oth_b_income,prem_income,"
          "out_prem,une_prem_reser,reins_income,n_sec_tb_income,n_sec_uw_income,"
          "n_asset_mg_income,oth_b_income,fv_value_chg_gain,invest_income,"
          "ass_invest_income,forex_gain,total_cogs,oper_cost,int_exp,comm_exp,"
          "biz_tax_surchg,sell_exp,admin_exp,fin_exp,assets_impair_loss,"
          "prem_refund,compens_payout,reser_insur_liab,div_payt,reins_exp,"
          "oper_exp,compens_payout_refu,insur_reser_refu,reins_cost_refund,"
          "other_bus_cost,operate_profit,non_oper_income,non_oper_exp,"
          "nca_disploss,total_profit,income_tax,n_income,n_income_attr_p,"
          "minority_gain,oth_compr_income,t_compr_income,compr_inc_attr_p,"
          "compr_inc_attr_m_s,ebit,ebitda,insurance_exp,undist_profit,"
          "distable_profit,rd_exp,fin_exp_int_exp,fin_exp_int_inc,"
          "transfer_surplus_rese,transfer_housing_imprest,transfer_oth,"
          "adj_lossgain,withdra_legal_surplus,withdra_legal_pubfund,"
          "withdra_biz_devfund,withdra_rese_fund,withdra_oth_ersu,"
          "workers_welfare,distr_profit_shrhder,prfshare_payable_dvd,"
          "comshare_payable_dvd,capit_comstock_div,net_after_nr_lp_correct,"
          "credit_impa_loss,net_expo_hedging_benefits,oth_impair_loss_assets,"
          "total_opcost,amodcost_fin_assets,oth_income,asset_disp_income,"
          "continued_net_profit")
COLS = FIELDS.split(",")
PK   = ["ts_code", "end_date", "report_type"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code                   VARCHAR(15) NOT NULL,
    ann_date                  DATE,
    f_ann_date                DATE,
    end_date                  DATE        NOT NULL,
    report_type               VARCHAR(5)  NOT NULL,
    comp_type                 VARCHAR(5),
    end_type                  VARCHAR(5),
    basic_eps                 FLOAT, diluted_eps               FLOAT,
    total_revenue             FLOAT, revenue                   FLOAT,
    int_income                FLOAT, prem_earned               FLOAT,
    comm_income               FLOAT, n_commis_income           FLOAT,
    n_oth_income              FLOAT, n_oth_b_income            FLOAT,
    prem_income               FLOAT, out_prem                  FLOAT,
    une_prem_reser            FLOAT, reins_income              FLOAT,
    n_sec_tb_income           FLOAT, n_sec_uw_income           FLOAT,
    n_asset_mg_income         FLOAT, oth_b_income              FLOAT,
    fv_value_chg_gain         FLOAT, invest_income             FLOAT,
    ass_invest_income         FLOAT, forex_gain                FLOAT,
    total_cogs                FLOAT, oper_cost                 FLOAT,
    int_exp                   FLOAT, comm_exp                  FLOAT,
    biz_tax_surchg            FLOAT, sell_exp                  FLOAT,
    admin_exp                 FLOAT, fin_exp                   FLOAT,
    assets_impair_loss        FLOAT, prem_refund               FLOAT,
    compens_payout            FLOAT, reser_insur_liab          FLOAT,
    div_payt                  FLOAT, reins_exp                 FLOAT,
    oper_exp                  FLOAT, compens_payout_refu       FLOAT,
    insur_reser_refu          FLOAT, reins_cost_refund         FLOAT,
    other_bus_cost            FLOAT, operate_profit            FLOAT,
    non_oper_income           FLOAT, non_oper_exp              FLOAT,
    nca_disploss              FLOAT, total_profit              FLOAT,
    income_tax                FLOAT, n_income                  FLOAT,
    n_income_attr_p           FLOAT, minority_gain             FLOAT,
    oth_compr_income          FLOAT, t_compr_income            FLOAT,
    compr_inc_attr_p          FLOAT, compr_inc_attr_m_s        FLOAT,
    ebit                      FLOAT, ebitda                    FLOAT,
    insurance_exp             FLOAT, undist_profit             FLOAT,
    distable_profit           FLOAT, rd_exp                    FLOAT,
    fin_exp_int_exp           FLOAT, fin_exp_int_inc           FLOAT,
    transfer_surplus_rese     FLOAT, transfer_housing_imprest  FLOAT,
    transfer_oth              FLOAT, adj_lossgain              FLOAT,
    withdra_legal_surplus     FLOAT, withdra_legal_pubfund     FLOAT,
    withdra_biz_devfund       FLOAT, withdra_rese_fund         FLOAT,
    withdra_oth_ersu          FLOAT, workers_welfare           FLOAT,
    distr_profit_shrhder      FLOAT, prfshare_payable_dvd      FLOAT,
    comshare_payable_dvd      FLOAT, capit_comstock_div        FLOAT,
    net_after_nr_lp_correct   FLOAT, credit_impa_loss          FLOAT,
    net_expo_hedging_benefits FLOAT, oth_impair_loss_assets    FLOAT,
    total_opcost              FLOAT, amodcost_fin_assets       FLOAT,
    oth_income                FLOAT, asset_disp_income         FLOAT,
    continued_net_profit      FLOAT,
    update_time               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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


def normalize_income_df(df):
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
        df = pro.income_vip(
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
        df = pro.income(
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
    print(f"[模式] income_vip 按公告日分页同步 start_date={start}, end_date={end}, page_size={page_size}")
    total_rows, t0 = 0, datetime.now()
    for page_no, df in enumerate(fetch_vip_pages(pro, start, end, FIELDS, page_size), 1):
        df = normalize_income_df(df)
        rows = upsert_latest_df(engine, df, TABLE, COLS, PK)
        total_rows += rows
        elapsed = (datetime.now() - t0).seconds
        print(f"  [VIP第{page_no:03d}页] {rows}条  累计{total_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
    return total_rows


def sync_by_normal_batches(pro, engine, start, end, batch_size):
    print(f"[模式] income 普通接口按股票批量同步 start_date={start}, end_date={end}, batch_size={batch_size}")
    codes = get_all_stock_codes(pro)
    total_rows, t0 = 0, datetime.now()
    total_batches = (len(codes) + batch_size - 1) // batch_size
    for i, (batch, df) in enumerate(fetch_normal_batches(pro, codes, start, end, FIELDS, batch_size), 1):
        df = normalize_income_df(df)
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
                        help="auto: 优先 income_vip，失败回退普通批量；vip: 只用 VIP；normal: 只用普通批量")
    parser.add_argument("--page-size", type=int, default=2000,
                        help="income_vip 分页大小")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="普通 income 每次请求拼接的股票数量")
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
            print(f"[WARN] income_vip 失败，回退普通批量模式: {e}", flush=True)
            total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)
    else:
        total_rows = sync_by_normal_batches(pro, engine, start, args.end, args.batch_size)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
