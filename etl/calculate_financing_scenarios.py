"""
Step 5 — compares financing structure costs (open account / factoring / LC /
SCF) layered on the real CCC balances from financial_ratios.
"""

import sqlite3
from datetime import date, datetime

DB_PATH = "db/mavi_treasury.db"
COMPANY_ID = 1


def get_rate(cur, period_ym, rate_type):
    cur.execute(
        "SELECT rate_pct FROM financing_rates_raw WHERE period LIKE ? AND rate_type=?",
        (period_ym + "%", rate_type),
    )
    row = cur.fetchone()
    return row[0] if row else None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT period_end, fiscal_year, fiscal_quarter, inventory,
               accounts_receivable, accounts_payable
        FROM financial_ratios
        WHERE company_id = ?
        ORDER BY period_end
        """,
        (COMPANY_ID,),
    )
    rows = cur.fetchall()

    for i, row in enumerate(rows):
        period_end = row["period_end"]
        period_ym = period_end[:7]
        inv, ar, ap = row["inventory"], row["accounts_receivable"], row["accounts_payable"]

        if i > 0:
            d1 = date.fromisoformat(rows[i - 1]["period_end"])
            d2 = date.fromisoformat(period_end)
            days = (d2 - d1).days
        else:
            days = 91

        comm_rate = get_rate(cur, period_ym, "commercial_loan")
        fact_rate = get_rate(cur, period_ym, "factoring")
        lc_rate = get_rate(cur, period_ym, "lc_commission")

        if None in (comm_rate, fact_rate, lc_rate):
            print(f"SKIP {period_end}: missing rate(s) - comm={comm_rate}, fact={fact_rate}, lc={lc_rate}")
            continue

        net_wc = inv + ar - ap
        baseline_cost = net_wc * (comm_rate / 100) * (days / 365)
        factoring_ar_cost = ar * (fact_rate / 100) * (days / 365)
        baseline_ar_cost = ar * (comm_rate / 100) * (days / 365)
        factoring_saving = baseline_ar_cost - factoring_ar_cost
        lc_ap_cost = ap * (lc_rate / 100) * (days / 365)
        scf_ap_cost = ap * (comm_rate / 100) * (days / 365)
        lc_vs_scf_saving = None  # not a fair comparison — see note below
        lc_scf_note = (
            "LC cost is a flat guarantee/service fee on the AP balance; SCF cost "
            "assumes the full AP balance is actively financed at the commercial "
            "loan rate. These serve different purposes (risk mitigation vs. "
            "liquidity access) and are not directly comparable as computed here."
        )    
   
        print(f"{period_end}: baseline_WC_cost={baseline_cost:+.0f}k, "
              f"factoring_saving={factoring_saving:+.0f}k, LC_cost={lc_ap_cost:+.0f}k, SCF_cost={scf_ap_cost:+.0f}k")

        cur.execute(
            """
            INSERT INTO financing_scenario_results
                (company_id, period_end, fiscal_year, fiscal_quarter, days_in_quarter,
                 inventory, accounts_receivable, accounts_payable,
                 commercial_loan_rate_pct, factoring_rate_pct, lc_commission_rate_pct,
                 baseline_wc_financing_cost_try, factoring_ar_cost_try,
                 factoring_vs_baseline_ar_saving_try, lc_ap_cost_try, scf_ap_cost_try,
                 lc_vs_scf_ap_saving_try, lc_scf_comparison_note, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(company_id, period_end) DO UPDATE SET
                days_in_quarter=excluded.days_in_quarter,
                inventory=excluded.inventory,
                accounts_receivable=excluded.accounts_receivable,
                accounts_payable=excluded.accounts_payable,
                commercial_loan_rate_pct=excluded.commercial_loan_rate_pct,
                factoring_rate_pct=excluded.factoring_rate_pct,
                lc_commission_rate_pct=excluded.lc_commission_rate_pct,
                baseline_wc_financing_cost_try=excluded.baseline_wc_financing_cost_try,
                factoring_ar_cost_try=excluded.factoring_ar_cost_try,
                factoring_vs_baseline_ar_saving_try=excluded.factoring_vs_baseline_ar_saving_try,
                lc_ap_cost_try=excluded.lc_ap_cost_try,
                scf_ap_cost_try=excluded.scf_ap_cost_try,
                lc_vs_scf_ap_saving_try=excluded.lc_vs_scf_ap_saving_try,
                lc_scf_comparison_note=excluded.lc_scf_comparison_note,
                calculated_at=excluded.calculated_at
            """,
            (
                COMPANY_ID, period_end, row["fiscal_year"], row["fiscal_quarter"], days,
                inv, ar, ap, comm_rate, fact_rate, lc_rate,
                round(baseline_cost, 0), round(factoring_ar_cost, 0),
                round(factoring_saving, 0), round(lc_ap_cost, 0), round(scf_ap_cost, 0),
                lc_vs_scf_saving, lc_scf_note, datetime.now().isoformat(),
            ),
        )

    conn.commit()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()


             
