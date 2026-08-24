"""
Step 4 — Hedging backtest: forward (CIRP-derived) vs unhedged, per quarterly
recurring FX exposure. Options collar is a separate follow-on script once this
baseline is verified.
"""

import sqlite3
from datetime import datetime, timedelta

DB_PATH = "db/mavi_treasury.db"

# Known-good reference figures from prior validated work — used only to sanity
# check the derived native_amount, not written to the DB.
REFERENCE_NATIVE_AMOUNTS = {
    ("2025-07-31", "USD"): 20176,
    ("2025-07-31", "EUR"): -1020,
    ("2025-10-31", "USD"): 15812,
    ("2025-10-31", "EUR"): -1704,
    ("2026-01-31", "USD"): -2513,
    ("2026-01-31", "EUR"): -2482,
    ("2026-04-30", "USD"): 18312,
    ("2026-04-30", "EUR"): -1005,
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_spot_rate(cur, date_str, currency, rate_type="selling"):
    pair = f"{currency}TRY"
    cur.execute(
        """
        SELECT rate FROM fx_rates
        WHERE currency_pair=? AND rate_type=? AND rate_date<=?
        ORDER BY rate_date DESC LIMIT 1
        """,
        (pair, rate_type, date_str),
    )
    row = cur.fetchone()
    return row["rate"] if row else None


def get_interest_rate(cur, period_ym, currency):
    cur.execute(
        "SELECT rate_pct FROM interest_rates_raw WHERE period LIKE ? AND currency=? AND tenor='3M'",
        (period_ym + "%", currency),
    )
    row = cur.fetchone()
    return row["rate_pct"] if row else None


def compute_forward(spot, try_rate_pct, fx_rate_pct, n_days):
    i_try = try_rate_pct / 100
    i_fx = fx_rate_pct / 100
    return spot * (1 + i_try * n_days / 365) / (1 + i_fx * n_days / 365)


def main():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT company_id, period_end, item_name, currency_linked, direction, balance_try
        FROM fx_exposure_items
        WHERE exposure_type='balance_sheet'
        ORDER BY period_end, currency_linked
        """
    )
    exposures = cur.fetchall()

    # distinct sorted period_ends, to find each row's "next quarter" for settlement
    period_ends = sorted({r["period_end"] for r in exposures})

    for row in exposures:
        period_end = row["period_end"]
        currency = row["currency_linked"]
        direction = row["direction"]
        balance_try = row["balance_try"]
        company_id = row["company_id"]

        # 1. Derive native amount using the same-date spot rate (selling rate assumed;
        #    flagged for verification against known reference figures below)
        spot_start = get_spot_rate(cur, period_end, currency, "selling")
        if spot_start is None:
            print(f"SKIP: no spot rate found for {currency} on {period_end}")
            continue
        native_amount_k = round(balance_try / spot_start, 0)

        ref_key = (period_end, currency)
        if ref_key in REFERENCE_NATIVE_AMOUNTS:
            ref_val = REFERENCE_NATIVE_AMOUNTS[ref_key]
            diff_pct = abs(native_amount_k - ref_val) / abs(ref_val) * 100
            flag = "OK" if diff_pct < 1 else f"MISMATCH ({diff_pct:.1f}% off, expected {ref_val})"
            print(f"{period_end} {currency}: derived={native_amount_k:.0f}k, ref={ref_val}k -> {flag}")

        # 2. Determine hedge window: this quarter's exposure carries into the NEXT
        #    disclosed period_end
        idx = period_ends.index(period_end)
        if idx + 1 < len(period_ends):
            hedge_end = period_ends[idx + 1]
            status = "settled"
        else:
            hedge_end = None
            status = "pending"

        n_days = (
            (datetime.strptime(hedge_end, "%Y-%m-%d") - datetime.strptime(period_end, "%Y-%m-%d")).days
            if hedge_end else 91
        )

        # 3. Interest rates at hedge start (same month as period_end)
        period_ym = period_end[:7]
        try_rate = get_interest_rate(cur, period_ym, "TRY")
        fx_rate = get_interest_rate(cur, period_ym, currency)
        if try_rate is None or fx_rate is None:
            print(f"SKIP: missing interest rate for {currency} at {period_ym}")
            continue

        # 4. Forward rate via CIRP
        forward_rate = compute_forward(spot_start, try_rate, fx_rate, n_days)

        # 5. Realized P&L, forward vs unhedged (only if settled)
        spot_end = None
        pnl = None
        unhedged_pnl = None
        if status == "settled":
            spot_end = get_spot_rate(cur, hedge_end, currency, "selling")
            if spot_end is not None:
                pnl = round(native_amount_k * (forward_rate - spot_end), 0)
                unhedged_pnl = round(native_amount_k * (spot_end - spot_start), 0)

        cur.execute(
            """
            INSERT INTO hedging_backtest_results
                (company_id, period_end, currency_linked, direction, native_amount_k,
                 spot_at_hedge_start, hedge_end, spot_at_hedge_end, days_n,
                 try_rate_pct, fx_rate_pct, forward_rate, pnl_forward_vs_unhedged_try,
                 unhedged_pnl_try, status, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(company_id, period_end, currency_linked, direction) DO UPDATE SET
                native_amount_k=excluded.native_amount_k,
                spot_at_hedge_start=excluded.spot_at_hedge_start,
                hedge_end=excluded.hedge_end,
                spot_at_hedge_end=excluded.spot_at_hedge_end,
                days_n=excluded.days_n,
                try_rate_pct=excluded.try_rate_pct,
                fx_rate_pct=excluded.fx_rate_pct,
                forward_rate=excluded.forward_rate,
                pnl_forward_vs_unhedged_try=excluded.pnl_forward_vs_unhedged_try,
                unhedged_pnl_try=excluded.unhedged_pnl_try,
                status=excluded.status,
                calculated_at=excluded.calculated_at
            """,
            (
                company_id, period_end, currency, direction, native_amount_k,
                spot_start, hedge_end, spot_end, n_days,
                try_rate, fx_rate, round(forward_rate, 4), pnl,
                unhedged_pnl, status, datetime.now().isoformat(),
            ),
        )

        pnl_str = f"{pnl:+.0f}k TRY" if pnl is not None else "pending"
        unhedged_str = f"{unhedged_pnl:+.0f}k TRY" if unhedged_pnl is not None else "pending"
        print(f"  -> F={forward_rate:.4f}, status={status}, P&L(forward-unhedged)={pnl_str}")

    conn.commit()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
