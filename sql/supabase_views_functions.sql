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
--      The parties table must include `ledger_account_id` so creditor
--      and debtor ledgers mirror the desktop one-to-one links.
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
-- 0. Schema parity columns required for desktop mirroring.
-- -----------------------------------------------------------------
ALTER TABLE public.parties
    ADD COLUMN IF NOT EXISTS ledger_account_id INTEGER;

COMMENT ON COLUMN public.parties.ledger_account_id IS
'Desktop party -> ledger account link. Required for creditor/debtor ledger parity on mobile web.';

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
-- 7. Cash Book RPC.
--    Mirrors CashBookLogic.get_cash_book:
--      * Locates 'Cash Account' (fallback 'Cash') for the company.
--      * Opening balance = account.opening_balance (with Dr/Cr sign)
--        plus SUM(debit-credit) of entries BEFORE p_from_date.
--      * For each cash entry in the window, joins to the "other side"
--        of the same voucher_no to derive `particulars`.
--      * Running balance uses a window function so we don't need a
--        Python loop.
--    Return shape:
--      * `row_type = 'entry'`  : one per ledger entry, real numbers.
--      * `row_type = 'summary'`: always present (last row) so callers
--        that end up with an empty entry set still receive the
--        opening/closing balances.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS f_cash_book(int, date, date);
CREATE OR REPLACE FUNCTION f_cash_book(
    p_company_id int,
    p_from_date  date,
    p_to_date    date
)
RETURNS TABLE (
    -- Column names deliberately prefixed with `out_` so they never collide
    -- with any base-table column (ledger_accounts.opening_balance,
    -- ledger_entries.voucher_date etc). Same pattern as f_monthly_analysis.
    out_row_type         text,
    out_voucher_date     date,
    out_voucher_no       text,
    out_voucher_type     text,
    out_particulars      text,
    out_narration        text,
    out_debit            numeric,
    out_credit           numeric,
    out_running_balance  numeric,
    out_opening_balance  numeric,
    out_total_receipts   numeric,
    out_total_payments   numeric,
    out_closing_balance  numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_cash_id  int;
    v_opening  numeric := 0;
    v_ob_amt   numeric := 0;
    v_ob_type  text    := 'Dr';
BEGIN
    -- Locate the cash account: prefer 'Cash Account', then 'Cash'.
    SELECT la.id, COALESCE(la.opening_balance, 0), COALESCE(la.opening_balance_type, 'Dr')
      INTO v_cash_id, v_ob_amt, v_ob_type
      FROM ledger_accounts la
     WHERE la.company_id = p_company_id
       AND is_row_active(la.is_active)
       AND la.account_name = 'Cash Account'
     LIMIT 1;

    IF v_cash_id IS NULL THEN
        SELECT la.id, COALESCE(la.opening_balance, 0), COALESCE(la.opening_balance_type, 'Dr')
          INTO v_cash_id, v_ob_amt, v_ob_type
          FROM ledger_accounts la
         WHERE la.company_id = p_company_id
           AND is_row_active(la.is_active)
           AND la.account_name = 'Cash'
         LIMIT 1;
    END IF;

    IF v_cash_id IS NULL THEN
        -- No cash account: emit a single all-zero summary row so the
        -- caller still receives a well-formed payload.
        RETURN QUERY SELECT
            'summary'::text, NULL::date, NULL::text, NULL::text,
            NULL::text, NULL::text,
            NULL::numeric, NULL::numeric, NULL::numeric,
            0::numeric, 0::numeric, 0::numeric, 0::numeric;
        RETURN;
    END IF;

    -- Opening balance = signed opening + prior-period movement.
    v_opening := CASE WHEN v_ob_type = 'Dr' THEN v_ob_amt ELSE -v_ob_amt END;

    SELECT v_opening + COALESCE(SUM(ve.debit) - SUM(ve.credit), 0)::numeric
      INTO v_opening
      FROM v_ledger_entries_enriched ve
     WHERE ve.company_id = p_company_id
       AND ve.account_id = v_cash_id
       AND ve.voucher_date::date < p_from_date;

    RETURN QUERY
    WITH cash_entries AS (
        SELECT
            ve.entry_id                          AS c_entry_id,
            ve.voucher_date::date                AS c_voucher_date,
            COALESCE(ve.voucher_no, '')::text    AS c_voucher_no,
            COALESCE(ve.voucher_type, '')::text  AS c_voucher_type,
            COALESCE(ve.narration, '')::text     AS c_narration,
            COALESCE(ve.debit, 0)::numeric       AS c_debit,
            COALESCE(ve.credit, 0)::numeric      AS c_credit
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.account_id = v_cash_id
          AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
    ),
    with_contra AS (
        SELECT
            c.*,
            COALESCE(
                (
                    SELECT la.account_name::text
                    FROM ledger_entries le2
                    JOIN ledger_accounts la ON la.id = le2.account_id
                    WHERE le2.company_id = p_company_id
                      AND le2.voucher_no = c.c_voucher_no
                      AND le2.id != c.c_entry_id
                      AND le2.account_id != v_cash_id
                      AND COALESCE(le2.voucher_type, '') NOT IN (
                            'quotation', 'estimate', 'quote',
                            'Quotation', 'Estimate', 'Quote'
                      )
                    LIMIT 1
                ),
                'Unknown'
            ) AS c_particulars
        FROM cash_entries c
    ),
    ordered AS (
        SELECT
            wc.*,
            ROW_NUMBER() OVER (ORDER BY wc.c_voucher_date, wc.c_entry_id) AS c_rn
        FROM with_contra wc
    ),
    with_running AS (
        SELECT
            o.*,
            v_opening + SUM(o.c_debit - o.c_credit) OVER (
                ORDER BY o.c_rn
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS c_running_balance
        FROM ordered o
    ),
    period_totals AS (
        SELECT
            COALESCE(SUM(ve.debit),  0)::numeric AS agg_receipts,
            COALESCE(SUM(ve.credit), 0)::numeric AS agg_payments
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.account_id = v_cash_id
          AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
    )
    -- Entry rows first.
    SELECT
        'entry'::text                            AS out_row_type,
        w.c_voucher_date                         AS out_voucher_date,
        w.c_voucher_no                           AS out_voucher_no,
        w.c_voucher_type                         AS out_voucher_type,
        w.c_particulars                          AS out_particulars,
        w.c_narration                            AS out_narration,
        w.c_debit                                AS out_debit,
        w.c_credit                               AS out_credit,
        ROUND(w.c_running_balance, 2)::numeric   AS out_running_balance,
        NULL::numeric                            AS out_opening_balance,
        NULL::numeric                            AS out_total_receipts,
        NULL::numeric                            AS out_total_payments,
        NULL::numeric                            AS out_closing_balance
    FROM with_running w

    UNION ALL

    -- Always emit a summary row so callers with zero entries still get
    -- the opening / closing balances they need.
    SELECT
        'summary'::text                          AS out_row_type,
        NULL::date, NULL::text, NULL::text,
        NULL::text, NULL::text,
        NULL::numeric, NULL::numeric, NULL::numeric,
        ROUND(v_opening, 2)::numeric             AS out_opening_balance,
        ROUND(pt.agg_receipts, 2)::numeric       AS out_total_receipts,
        ROUND(pt.agg_payments, 2)::numeric       AS out_total_payments,
        ROUND(
            v_opening + pt.agg_receipts - pt.agg_payments, 2
        )::numeric                               AS out_closing_balance
    FROM period_totals pt

    -- Sort by SELECT-list ordinal so the OUT parameter name
    -- `out_row_type` never re-enters name resolution (which triggers
    -- SQLSTATE 42702 "column reference is ambiguous").
    -- Column 1 is out_row_type: 'entry' < 'summary' alphabetically, so
    -- ASC puts entry rows first and the summary row last. Column 2 is
    -- out_voucher_date; summary row's NULL date sits at the tail.
    ORDER BY 1 ASC, 2 ASC NULLS LAST;
END;
$$;

COMMENT ON FUNCTION f_cash_book(int, date, date) IS
'Cash Book mirroring CashBookLogic.get_cash_book. Returns entry rows plus a trailing summary row (row_type=summary) so opening/closing balances are always available.';


-- -----------------------------------------------------------------
-- 8. Ledger Statement RPC.
--    Mirrors LedgerLogic.get_account_ledger (the second definition
--    at ledger_logic.py:3089 which is the one called by
--    `_run_ledger_statement`). Structurally identical to f_cash_book
--    but the account is passed in explicitly instead of being
--    discovered from ledger_accounts.
--
--    Opening balance formula:
--        opening = signed ledger_accounts.opening_balance
--                + SUM(debit-credit) on v_ledger_entries_enriched
--                  where voucher_date < p_from_date
--
--    Per-row `particulars` comes from the contra account (same
--    voucher_no, different account_id, non-quote voucher_type) so the
--    Ledger Statement column that today renders empty finally shows
--    the actual "who was on the other side" value.
--
--    Return shape matches f_cash_book: `entry` rows first, one
--    trailing `summary` row always emitted so empty windows still
--    return opening/closing balances.
-- -----------------------------------------------------------------
DROP FUNCTION IF EXISTS f_ledger_statement(int, int, date, date);
CREATE OR REPLACE FUNCTION f_ledger_statement(
    p_company_id int,
    p_account_id int,
    p_from_date  date,
    p_to_date    date
)
RETURNS TABLE (
    -- `out_*` prefix keeps every OUT column out of PL/pgSQL name
    -- resolution so we never hit the SQLSTATE 42702 ambiguity trap
    -- that bit both f_monthly_analysis and f_cash_book during rollout.
    out_row_type         text,
    out_voucher_date     date,
    out_voucher_no       text,
    out_voucher_type     text,
    out_particulars      text,
    out_narration        text,
    out_debit            numeric,
    out_credit           numeric,
    out_running_balance  numeric,
    out_opening_balance  numeric,
    out_period_debit     numeric,
    out_period_credit    numeric,
    out_closing_balance  numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_account_exists boolean;
    v_ob_amt   numeric := 0;
    v_ob_type  text    := 'Dr';
    v_opening  numeric := 0;
BEGIN
    -- Validate the account belongs to the company (and is active).
    -- We deliberately require an exact account_id match; ledger-statement
    -- has no fallback discovery like cash-book because the caller is
    -- expected to pass an explicit selection.
    SELECT TRUE,
           COALESCE(la.opening_balance, 0),
           COALESCE(la.opening_balance_type, 'Dr')
      INTO v_account_exists, v_ob_amt, v_ob_type
      FROM ledger_accounts la
     WHERE la.company_id = p_company_id
       AND la.id = p_account_id
       AND is_row_active(la.is_active)
     LIMIT 1;

    IF NOT COALESCE(v_account_exists, FALSE) THEN
        -- Unknown / inactive account: emit a single zero summary row
        -- so callers still receive a well-formed payload.
        RETURN QUERY SELECT
            'summary'::text, NULL::date, NULL::text, NULL::text,
            NULL::text, NULL::text,
            NULL::numeric, NULL::numeric, NULL::numeric,
            0::numeric, 0::numeric, 0::numeric, 0::numeric;
        RETURN;
    END IF;

    -- Opening balance = signed opening + prior-period movement.
    v_opening := CASE WHEN v_ob_type = 'Dr' THEN v_ob_amt ELSE -v_ob_amt END;

    SELECT v_opening + COALESCE(SUM(ve.debit) - SUM(ve.credit), 0)::numeric
      INTO v_opening
      FROM v_ledger_entries_enriched ve
     WHERE ve.company_id = p_company_id
       AND ve.account_id = p_account_id
       AND ve.voucher_date::date < p_from_date;

    RETURN QUERY
    WITH acct_entries AS (
        SELECT
            ve.entry_id                          AS c_entry_id,
            ve.voucher_date::date                AS c_voucher_date,
            COALESCE(ve.voucher_no, '')::text    AS c_voucher_no,
            COALESCE(ve.voucher_type, '')::text  AS c_voucher_type,
            COALESCE(ve.narration, '')::text     AS c_narration,
            COALESCE(ve.debit, 0)::numeric       AS c_debit,
            COALESCE(ve.credit, 0)::numeric      AS c_credit
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.account_id = p_account_id
          AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
    ),
    with_contra AS (
        SELECT
            a.*,
            COALESCE(
                (
                    -- Same voucher, the *other* posting leg. Excludes
                    -- self and quotation-style vouchers to match
                    -- desktop LedgerLogic filtering.
                    SELECT la.account_name::text
                    FROM ledger_entries le2
                    JOIN ledger_accounts la ON la.id = le2.account_id
                    WHERE le2.company_id = p_company_id
                      AND le2.voucher_no = a.c_voucher_no
                      AND le2.id != a.c_entry_id
                      AND le2.account_id != p_account_id
                      AND COALESCE(le2.voucher_type, '') NOT IN (
                            'quotation', 'estimate', 'quote',
                            'Quotation', 'Estimate', 'Quote'
                      )
                    LIMIT 1
                ),
                'Unknown'
            ) AS c_particulars
        FROM acct_entries a
    ),
    ordered AS (
        SELECT
            wc.*,
            ROW_NUMBER() OVER (ORDER BY wc.c_voucher_date, wc.c_entry_id) AS c_rn
        FROM with_contra wc
    ),
    with_running AS (
        SELECT
            o.*,
            v_opening + SUM(o.c_debit - o.c_credit) OVER (
                ORDER BY o.c_rn
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS c_running_balance
        FROM ordered o
    ),
    period_totals AS (
        SELECT
            COALESCE(SUM(ve.debit),  0)::numeric AS agg_debit,
            COALESCE(SUM(ve.credit), 0)::numeric AS agg_credit
        FROM v_ledger_entries_enriched ve
        WHERE ve.company_id = p_company_id
          AND ve.account_id = p_account_id
          AND ve.voucher_date::date BETWEEN p_from_date AND p_to_date
    )
    -- Entry rows first.
    SELECT
        'entry'::text                            AS out_row_type,
        w.c_voucher_date                         AS out_voucher_date,
        w.c_voucher_no                           AS out_voucher_no,
        w.c_voucher_type                         AS out_voucher_type,
        w.c_particulars                          AS out_particulars,
        w.c_narration                            AS out_narration,
        w.c_debit                                AS out_debit,
        w.c_credit                               AS out_credit,
        ROUND(w.c_running_balance, 2)::numeric   AS out_running_balance,
        NULL::numeric                            AS out_opening_balance,
        NULL::numeric                            AS out_period_debit,
        NULL::numeric                            AS out_period_credit,
        NULL::numeric                            AS out_closing_balance
    FROM with_running w

    UNION ALL

    -- Trailing summary row.
    SELECT
        'summary'::text                          AS out_row_type,
        NULL::date, NULL::text, NULL::text,
        NULL::text, NULL::text,
        NULL::numeric, NULL::numeric, NULL::numeric,
        ROUND(v_opening, 2)::numeric             AS out_opening_balance,
        ROUND(pt.agg_debit, 2)::numeric          AS out_period_debit,
        ROUND(pt.agg_credit, 2)::numeric         AS out_period_credit,
        ROUND(
            v_opening + pt.agg_debit - pt.agg_credit, 2
        )::numeric                               AS out_closing_balance
    FROM period_totals pt

    -- Column ordinals, not names — ambiguity-safe.
    -- Col 1 out_row_type: 'entry' < 'summary' ASC so entries lead.
    -- Col 2 out_voucher_date: NULL (from summary row) sorts last.
    ORDER BY 1 ASC, 2 ASC NULLS LAST;
END;
$$;

COMMENT ON FUNCTION f_ledger_statement(int, int, date, date) IS
'Ledger Statement mirroring LedgerLogic.get_account_ledger. Returns entry rows + one trailing summary row (row_type=summary) so opening/period/closing figures are always available even when the entry window is empty.';


-- -----------------------------------------------------------------
-- 9. Sanity checks (run these once after install).
-- -----------------------------------------------------------------
--   select count(*) from v_ledger_entries_enriched;
--   select * from f_trial_balance(25, '2024-04-01', '2026-06-30', 'All', null) limit 5;
--   select * from f_monthly_analysis(25, '2024-04-01', '2026-06-30') limit 5;
--   select * from f_day_book_entries(25, '2024-04-01', '2024-04-30') limit 5;
