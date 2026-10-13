"""Ma'lumotlar sifatini tekshirish (Data Quality). Har bir tekshiruv - "xato qatorlar sonini" qaytaruvchi SQL."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    sql: str
    severity: str = "error"   # error -> run muvaffaqiyatsiz, warn -> faqat ogohlantirish


CHECKS = [
    Check("fact_pk_unique",
          "SELECT count(*) - count(DISTINCT contract_id) FROM fact_contract"),
    Check("fact_required_not_null",
          "SELECT count(*) FROM fact_contract WHERE org_inn IS NULL OR supplier_inn IS NULL OR amount_uzs IS NULL"),
    Check("fact_amount_positive",
          "SELECT count(*) FROM fact_contract WHERE amount_uzs <= 0"),
    Check("fk_organization",
          "SELECT count(*) FROM fact_contract f ANTI JOIN dim_organization o USING (org_inn)"),
    Check("fk_supplier",
          "SELECT count(*) FROM fact_contract f ANTI JOIN dim_supplier s USING (supplier_inn)"),
    Check("fk_date",
          "SELECT count(*) FROM fact_contract f ANTI JOIN dim_date d USING (date_key)"),
    Check("amount_matches_qty_x_price",
          "SELECT count(*) FROM fact_contract WHERE abs(amount - quantity * unit_price) > 0.01"),
    Check("future_contract_date",
          "SELECT count(*) FROM fact_contract f JOIN dim_date d USING (date_key) WHERE d.full_date > current_date"),
    Check("fx_rate_fallback_used",
          "SELECT count(*) FROM dim_currency_rate WHERE source = 'fallback'", severity="warn"),
    Check("quarantine_ratio_below_5pct",
          """SELECT CASE WHEN q.n > 0.05 * (q.n + f.n) THEN q.n ELSE 0 END
             FROM (SELECT count(*) n FROM quarantine_contract WHERE run_id = $run_id) q,
                  (SELECT count(*) n FROM fact_contract WHERE run_id = $run_id) f""",
          severity="warn"),
]


def run_checks(con, run_id: int) -> list[dict]:
    results = []
    for c in CHECKS:
        params = {"run_id": run_id} if "$run_id" in c.sql else None
        failed = con.execute(c.sql, params).fetchone()[0] if params else con.execute(c.sql).fetchone()[0]
        passed = failed == 0
        con.execute("INSERT INTO dq_check_result (run_id, check_name, severity, failed_rows, passed) VALUES (?, ?, ?, ?, ?)",
                    [run_id, c.name, c.severity, failed, passed])
        results.append({"check": c.name, "severity": c.severity, "failed_rows": failed, "passed": passed})
    return results
