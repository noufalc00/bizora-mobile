-- =====================================================================
-- Faizan Pro Accounting - Supabase (PostgreSQL) fast-path views + RPCs
-- =====================================================================
-- Purpose:
--   Pre-aggregate ledger data so the web dashboard's Trial Balance,
--   Monthly Analysis, and Day Book routes can query Postgres directly
--   without hydrating a temporary SQLite snapshot on every request.
--
-- How to apply:
--   1. Open Supabase -> SQL Editor -> New query.
--   2. Paste this entire file and click "Run".
--   3. Re-run `sync_bulk_to_supabase.py` at least once so the base
--      tables contain the latest ledger_accounts + ledger_entries data.
--
-- Contracts (must match desktop logic 1:1):
--   * Excludes voucher_type values that live in this array:
--       ('quotation', 'estimate', 'quote',
--        'Quotation', 'Estimate', 'Quote')
--   * Opening balance sign convention: Dr positive, Cr negative.
--   * Trial Balance closing = opening + (period_debit - period_credit),
--     split back into Dr/Cr columns without negative values.
--   * Monthly Analysis: income accounts contribute (credit - debit),
--     expense accounts contribute (debit - credit).
--   * Trading income tokens: 'sales', 'purchase return'.
--   * Direct expense tokens: 'purchase', 'sales return', 'freight',
--     'direct labour', 'direct labor', 'carriage',
--     'direct expense', 'wages'.
-- =====================================================================

-- -----------------------------------------------------------------
-- 1. Enriched ledger entries: joins account_name / account_type once.
-- -----------------------------------------------------------------
DROP VIEW IF EXISTS v_ledger_entries_enriched CASCADE;
CREATE VIEW v_ledger_entries_enriched AS
SELECT
    le.id                                    AS entry_id,
    le.company_id                            AS company_id,
    le.account_id                            AS account_id,
    la.account_name                          AS account_name,
    la.account_type                          AS account_type,
    COALESCE(la.group_name, '')              AS group_name,
    le.voucher_date                          AS voucher_date,
    le.voucher_type                          AS voucher_type,
    le.voucher_id                            AS voucher_id,
    le.voucher_no                            AS voucher_no,
    le.narration                             AS narration,
    COALESCE(le.debit, 0)                    AS debit,
    COALESCE(le.credit, 0)                   AS credit
FROM ledger_entries le
INNER JOIN ledger_accounts la
        ON la.id = le.account_id
       AND la.company_id = le.company_id
WHERE COALESCE(le.voucher_type, '') NOT IN (
    'quotation', 'estimate', 'quote',
    'Quotation', 'Estimate', 'Quote'
);

COMMENT ON VIEW v_ledger_entries_enriched IS
'Ledger entries joined with account metadata. Excludes quotations/estimates so it matches DayBookLogic and FinancialReportingEngine.';

-- -----------------------------------------------------------------
-- 2. Daily per-account debit/credit totals.
-- -----------------------------------------------------------------
DROP VIEW IF EXISTS v_ledger_daily_totals CASCADE;
CREATE VIEW v_ledger_daily_totals AS
SELECT
    company_id,
    account_id,
    account_name,
    account_type,
    group_name,
    voucher_date::date                       AS voucher_date,
    SUM(debit)                               AS debit_total,
    SUM(credit)                              AS credit_total
FROM v_ledger_entries_enriched
GROUP BY
    company_id, account_id, account_name, account_type, group_name, voucher_date::date;

-- -----------------------------------------------------------------
-- 3. Monthly per-account debit/credit totals with signed impact.
--    Used by Monthly Analysis and Profit & Loss.
-- -----------------------------------------------------------------
DROP VIEW IF EXISTS v_ledger_monthly_totals CASCADE;
CREATE VIEW v_ledger_monthly_totals AS
SELECT
    company_id,
    account_id,
    account_name,
    account_type,
    group_name,
    EXTRACT(YEAR  FROM voucher_date::date)::int  AS fy_year,
    EXTRACT(MONTH FROM voucher_date::date)::int  AS fy_month,
    SUM(debit)                                   AS debit_total,
    SUM(credit)                                  AS credit_total,
    CASE
        WHEN LOWER(TRIM(account_type)) = 'income'
             THEN SUM(credit) - SUM(debit)
        ELSE SUM(debit) - SUM(credit)
    END                                          AS signed_impact
FROM v_ledger_entries_enriched
GROUP BY
    company_id, account_id, account_name, account_type, group_name,
    EXTRACT(YEAR  FROM voucher_date::date),
    EXTRACT(MONTH FROM voucher_date::date);

-- -----------------------------------------------------------------
-- Helper: normalize is_active values across INTEGER / BOOLEAN / TEXT.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS is_row_active(anyelement);
CREATE OR REPLACE FUNCTION is_row_active(v anyelement)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    txt text;
BEGIN
    IF v IS NULL THEN
        RETURN TRUE;
    END IF;
    txt := LOWER(TRIM(v::text));
    IF txt IN ('0', 'false', 'f', 'no', 'n') THEN
        RETURN FALSE;
    END IF;
    RETURN TRUE;
END;
$$;

COMMENT ON FUNCTION is_row_active(anyelement) IS
'Return TRUE unless the value is explicitly 0/false/no. Works for INTEGER, BOOLEAN, TEXT.';


-- -----------------------------------------------------------------
-- 4. Trial Balance RPC.
--    Mirrors FinancialReportingEngine.generate_trial_balance.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS f_trial_balance(int, date, date, text, text);
CREATE OR REPLACE FUNCTION f_trial_balance(
    p_company_id       int,
    p_from_date        date,
    p_to_date          date,
    p_account_type     text DEFAULT NULL,   -- 'Cash/Bank','Party','Income',...
    p_search           text DEFAULT NULL
)
RETURNS TABLE (
    sl_no           int,
    account_id      int,
    account_name    text,
    account_type    text,
    group_name      text,
    opening_debit   numeric,
    opening_credit  numeric,
    period_debit    numeric,
    period_credit   numeric,
    closing_debit   numeric,
    closing_credit  numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_type_filter text[];
BEGIN
    v_type_filter := CASE p_account_type
        WHEN 'Cash/Bank' THEN ARRAY['cash_bank']
        WHEN 'Party'     THEN ARRAY['party']
        WHEN 'Income'    THEN ARRAY['income']
        WHEN 'Expense'   THEN ARRAY['expense']
        WHEN 'Tax'       THEN ARRAY['tax_liability']
        WHEN 'Capital'   THEN ARRAY['capital']
        WHEN 'Stock'     THEN ARRAY['stock']
        WHEN 'Asset'     THEN ARRAY['cash_bank','party','stock']
        WHEN 'Liability' THEN ARRAY['party','tax_liability']
        ELSE NULL
    END;

    RETURN QUERY
    WITH accounts AS (
        SELECT
            la.id::int                                                 AS id,
            la.account_name::text                                      AS account_name,
            LOWER(TRIM(la.account_type::text))                          AS account_type,
            COALESCE(la.group_name, '')::text                           AS group_name,
            COALESCE(la.opening_balance, 0)::numeric                    AS opening_balance,
            COALESCE(la.opening_balance_type, 'Dr')::text               AS opening_balance_type
        FROM ledger_accounts la
        WHERE la.company_id = p_company_id
          AND is_row_active(la.is_active)
          AND (
              v_type_filter IS NULL
              OR LOWER(TRIM(la.account_type::text)) = ANY (
                  SELECT LOWER(TRIM(x)) FROM unnest(v_type_filter) AS x
              )
          )
          AND (
              p_search IS NULL
              OR TRIM(p_search) = ''
              OR la.account_name ILIKE '%' || TRIM(p_search) || '%'
          )
    ),
    opening AS (
        SELECT
            ve.account_id::int AS account_id,
            SUM(ve.debit)::numeric  AS dr,
            SUM(ve.credit)::numeric AS cr
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.voucher_date::date < p_from_date
        GROUP BY ve.account_id
    ),
    period AS (
        SELECT
            ve.account_id::int AS account_id,
            SUM(ve.debit)::numeric  AS dr,
            SUM(ve.credit)::numeric AS cr
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
        GROUP BY ve.account_id
    ),
    computed AS (
        SELECT
            a.id,
            a.account_name,
            a.account_type,
            a.group_name,
            (CASE WHEN a.opening_balance_type = 'Dr'
                  THEN a.opening_balance ELSE -a.opening_balance END
             + COALESCE(o.dr, 0) - COALESCE(o.cr, 0))                  AS opening_net,
            COALESCE(p.dr, 0)                                          AS period_dr,
            COALESCE(p.cr, 0)                                          AS period_cr
        FROM accounts a
        LEFT JOIN opening o ON o.account_id = a.id
        LEFT JOIN period  p ON p.account_id = a.id
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY c.account_type, c.account_name)::int,
        c.id::int,
        c.account_name::text,
        c.account_type::text,
        c.group_name::text,
        GREATEST(c.opening_net, 0)::numeric                             AS opening_debit,
        GREATEST(-c.opening_net, 0)::numeric                            AS opening_credit,
        c.period_dr::numeric                                            AS period_debit,
        c.period_cr::numeric                                            AS period_credit,
        GREATEST(c.opening_net + c.period_dr - c.period_cr, 0)::numeric AS closing_debit,
        GREATEST(-(c.opening_net + c.period_dr - c.period_cr), 0)::numeric AS closing_credit
    FROM computed c
    ORDER BY 1;
END;
$$;

COMMENT ON FUNCTION f_trial_balance(int, date, date, text, text) IS
'Trial Balance mirroring desktop generate_trial_balance. Tolerant of BOOLEAN / INTEGER / TEXT is_active.';

-- -----------------------------------------------------------------
-- 5. Monthly Analysis RPC.
--    Mirrors MonthlyAnalysisLogic.get_monthly_analysis.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS f_monthly_analysis(int, date, date);
CREATE OR REPLACE FUNCTION f_monthly_analysis(
    p_company_id int,
    p_from_date  date,
    p_to_date    date
)
RETURNS TABLE (
    out_fy_year            int,
    out_fy_month           int,
    out_month_name         text,
    out_trading_income     numeric,
    out_direct_expenses    numeric,
    out_indirect_income    numeric,
    out_indirect_expenses  numeric,
    out_gross_profit       numeric,
    out_net_profit         numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    WITH classified AS (
        SELECT
            m.fy_year                                       AS c_year,
            m.fy_month                                      AS c_month,
            CASE
                WHEN LOWER(TRIM(m.account_type)) = 'income' AND (
                        LOWER(m.account_name || ' ' || m.group_name) LIKE '%sales%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%purchase return%'
                     )
                     THEN 'trading_income'
                WHEN LOWER(TRIM(m.account_type)) = 'income'
                     THEN 'indirect_income'
                WHEN (
                        LOWER(m.account_name || ' ' || m.group_name) LIKE '%purchase%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%sales return%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%freight%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%direct labour%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%direct labor%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%carriage%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%direct expense%'
                     OR LOWER(m.account_name || ' ' || m.group_name) LIKE '%wages%'
                     )
                     THEN 'direct_expenses'
                ELSE 'indirect_expenses'
            END                                             AS bucket,
            m.signed_impact                                 AS amount
        FROM v_ledger_monthly_totals m
        WHERE m.company_id = p_company_id
          AND LOWER(TRIM(m.account_type)) IN ('income', 'expense')
          AND make_date(m.fy_year, m.fy_month, 1) BETWEEN date_trunc('month', p_from_date)::date
                                                       AND p_to_date
    ),
    aggregated AS (
        SELECT
            c_year,
            c_month,
            SUM(CASE WHEN bucket = 'trading_income'    THEN amount ELSE 0 END) AS agg_trading_income,
            SUM(CASE WHEN bucket = 'direct_expenses'   THEN amount ELSE 0 END) AS agg_direct_expenses,
            SUM(CASE WHEN bucket = 'indirect_income'   THEN amount ELSE 0 END) AS agg_indirect_income,
            SUM(CASE WHEN bucket = 'indirect_expenses' THEN amount ELSE 0 END) AS agg_indirect_expenses
        FROM classified
        GROUP BY c_year, c_month
    )
    SELECT
        a.c_year::int,
        a.c_month::int,
        TO_CHAR(make_date(a.c_year, a.c_month, 1), 'FMMonth')::text,
        ROUND(a.agg_trading_income,    2)::numeric,
        ROUND(a.agg_direct_expenses,   2)::numeric,
        ROUND(a.agg_indirect_income,   2)::numeric,
        ROUND(a.agg_indirect_expenses, 2)::numeric,
        ROUND(a.agg_trading_income - a.agg_direct_expenses, 2)::numeric,
        ROUND(a.agg_trading_income - a.agg_direct_expenses
              + a.agg_indirect_income - a.agg_indirect_expenses, 2)::numeric
    FROM aggregated a
    ORDER BY a.c_year, a.c_month;
END;
$$;

COMMENT ON FUNCTION f_monthly_analysis(int, date, date) IS
'Monthly Analysis rows matching MonthlyAnalysisLogic.get_monthly_analysis.';

-- -----------------------------------------------------------------
-- 6. Day Book RPC (per-day totals + full entry list).
--    Only the flat entry list is exposed here; the daily
--    opening/total/closing synthetic rows still come from
--    DayBookLogic on the desktop bridge, so parity is preserved.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS f_day_book_entries(int, date, date);
CREATE OR REPLACE FUNCTION f_day_book_entries(
    p_company_id int,
    p_from_date  date,
    p_to_date    date
)
RETURNS TABLE (
    voucher_date   date,
    voucher_no     text,
    voucher_type   text,
    account_id     int,
    account_name   text,
    account_type   text,
    debit          numeric,
    credit         numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        ve.voucher_date::date,
        ve.voucher_no::text,
        ve.voucher_type::text,
        ve.account_id,
        ve.account_name::text,
        ve.account_type::text,
        ve.debit,
        ve.credit
    FROM v_ledger_entries_enriched ve
    WHERE ve.company_id = p_company_id
      AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
    ORDER BY ve.voucher_date, ve.voucher_no, ve.entry_id;
$$;

COMMENT ON FUNCTION f_day_book_entries(int, date, date) IS
'Flat day book entries. DayBookLogic then adds daily opening/total/closing rows on top.';

-- -----------------------------------------------------------------
-- 7. Sanity checks (run these once after install).
-- -----------------------------------------------------------------
--   select count(*) from v_ledger_entries_enriched;
--   select * from f_trial_balance(25, '2024-04-01', '2026-06-30', 'All', null) limit 5;
--   select * from f_monthly_analysis(25, '2024-04-01', '2026-06-30') limit 5;
--   select * from f_day_book_entries(25, '2024-04-01', '2024-04-30') limit 5;
