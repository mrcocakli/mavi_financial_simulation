"""
Step 4b — Zero-cost options collar backtest, computed at multiple k (collar
width) values for sensitivity. Collar centered on the CIRP forward rate
already stored in hedging_backtest_results.
"""

import sqlite3
import math
from datetime import datetime

DB_PATH = "db/mavi_treasury.db"
K_VALUES = [0.5, 0.75, 1.0]
VOL_WINDOW_DAYS = 90


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


def realized_vol_annualized(cur, currency, as_of_date, window_days=VOL_WINDOW_DAYS):
    pair = f"{currency}TRY"
    cur.execute(
        """
        SELECT rate_date, rate FROM fx_rates
        WHERE currency_pair=? AND rate_type='selling' AND rate_date<?
        ORDER BY rate_date DESC LIMIT ?
        """,
        (pair, as_of_date, window_days + 1),
    )
    rows = cur.fetchall()
    rates = [r["rate"] for r in rows][::-1]  # chronological order
    if len(rates) < 10:
        return None
    log_returns = [math.log(rates[i] / rates[i - 1]) for i in range(1, len(rates))]
    mean_r = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_r) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_std = math.sqrt(variance)
    return daily_std * math.sqrt(252)


def main():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT company_id, period_end, currency_linked, direction, native_amount_k,
               spot_at_hedge_start, forward_rate, hedge_end, spot_at_hedge_end,
               days_n, status
        FROM hedging_backtest_results
        ORDER BY period_end, currency_linked
        """
    )
    rows = cur.fetchall()

    for row in rows:
        currency = row["currency_linked"]
        period_end = row["period_end"]
        n_days = row["days_n"]
        forward_rate = row["forward_rate"]

        sigma = realized_vol_annualized(cur, currency, period_end)
        if sigma is None:
            print(f"SKIP {period_end} {currency}: insufficient history for vol calc")
            continue

        time_scaling = math.sqrt(n_days / 365)

        for k in K_VALUES:
            call_strike = forward_rate * (1 + k * sigma * time_scaling)
            put_strike = forward_rate * (1 - k * sigma * time_scaling)

            settlement_rate = None
            pnl = None
            if row["status"] == "settled" and row["spot_at_hedge_end"] is not None:
                spot_end = row["spot_at_hedge_end"]
                settlement_rate = min(max(spot_end, put_strike), call_strike)
                pnl = round(row["native_amount_k"] * (settlement_rate - spot_end), 0)

            cur.execute(
                """
                INSERT INTO options_collar_results
                    (company_id, period_end, currency_linked, direction, native_amount_k,
                     forward_rate, realized_vol_annualized, k_factor, call_strike, put_strike,
                     hedge_end, spot_at_hedge_end, settlement_rate, pnl_collar_vs_unhedged_try,
                     status, calculated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(company_id, period_end, currency_linked, direction, k_factor) DO UPDATE SET
                    native_amount_k=excluded.native_amount_k,
                    forward_rate=excluded.forward_rate,
                    realized_vol_annualized=excluded.realized_vol_annualized,
                    call_strike=excluded.call_strike,
                    put_strike=excluded.put_strike,
                    hedge_end=excluded.hedge_end,
                    spot_at_hedge_end=excluded.spot_at_hedge_end,
                    settlement_rate=excluded.settlement_rate,
                    pnl_collar_vs_unhedged_try=excluded.pnl_collar_vs_unhedged_try,
                    status=excluded.status,
                    calculated_at=excluded.calculated_at
                """,
                (
                    row["company_id"], period_end, currency, row["direction"],
                    row["native_amount_k"], forward_rate, round(sigma, 4), k,
                    round(call_strike, 4), round(put_strike, 4),
                    row["hedge_end"], row["spot_at_hedge_end"], settlement_rate,
                    pnl, row["status"], datetime.now().isoformat(),
                ),
            )

            pnl_str = f"{pnl:+.0f}k TRY" if pnl is not None else "pending"
            print(f"{period_end} {currency} k={k}: put={put_strike:.4f} call={call_strike:.4f} "
                  f"-> collar P&L(vs unhedged)={pnl_str}")

        conn.commit()

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
