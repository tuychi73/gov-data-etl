"""DuckDB ma'lumotlar omboriga yuklash (Load bosqichi). Barcha yuklashlar idempotent (upsert)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from etl.config import PROJECT_ROOT

SQL_DIR = PROJECT_ROOT / "sql"


def connect(path: Path | str) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    con.execute((SQL_DIR / "marts.sql").read_text(encoding="utf-8"))


# ---------- run log va holat (watermark) ----------

def start_run(con) -> int:
    run_id = con.execute("SELECT nextval('seq_run_id')").fetchone()[0]
    con.execute("INSERT INTO etl_run_log (run_id, started_at, status) VALUES (?, current_timestamp, 'running')", [run_id])
    return run_id


def finish_run(con, run_id: int, status: str, *, extracted=0, loaded=0, rejected=0,
               watermark: datetime | None = None, message: str | None = None) -> None:
    con.execute("""
        UPDATE etl_run_log
        SET finished_at = current_timestamp, status = ?, extracted = ?, loaded = ?, rejected = ?,
            watermark = ?, message = ?
        WHERE run_id = ?""", [status, extracted, loaded, rejected, watermark, message, run_id])


def get_state(con, key: str) -> str | None:
    row = con.execute("SELECT value FROM etl_state WHERE key = ?", [key]).fetchone()
    return row[0] if row else None


def set_state(con, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO etl_state VALUES (?, ?)", [key, value])


# ---------- valyuta kurslari ----------

def known_rate_keys(con) -> set[tuple]:
    return {(d, c) for d, c in con.execute("SELECT rate_date, currency FROM dim_currency_rate").fetchall()}


def load_rates(con, rates: pd.DataFrame) -> None:
    if rates.empty:
        return
    con.register("stg_rates", rates)
    con.execute("""
        INSERT OR REPLACE INTO dim_currency_rate (rate_date, currency, rate_uzs, source)
        SELECT CAST(rate_date AS DATE), currency, rate_uzs, source FROM stg_rates""")
    con.unregister("stg_rates")


def all_rates(con) -> pd.DataFrame:
    return con.execute("SELECT rate_date, currency, rate_uzs FROM dim_currency_rate").df()


# ---------- o'lchovlar va faktlar ----------

def load_dimensions(con, df: pd.DataFrame) -> None:
    con.register("stg", df)
    con.execute("""
        INSERT INTO dim_organization
        SELECT org_inn, any_value(org_name), any_value(region), max(updated_at) FROM stg GROUP BY org_inn
        ON CONFLICT (org_inn) DO UPDATE
            SET org_name = excluded.org_name, region = excluded.region, updated_at = excluded.updated_at""")
    con.execute("""
        INSERT INTO dim_supplier
        SELECT supplier_inn, any_value(supplier_name), min(contract_date), max(updated_at) FROM stg GROUP BY supplier_inn
        ON CONFLICT (supplier_inn) DO UPDATE
            SET supplier_name = excluded.supplier_name,
                first_seen = least(dim_supplier.first_seen, excluded.first_seen),
                updated_at = excluded.updated_at""")
    con.execute("""
        INSERT OR REPLACE INTO dim_product
        SELECT product_code, any_value(product_name) FROM stg GROUP BY product_code""")
    con.execute("""
        INSERT INTO dim_date
        SELECT DISTINCT
               CAST(strftime(contract_date, '%Y%m%d') AS INTEGER),
               contract_date,
               year(contract_date), quarter(contract_date), month(contract_date),
               isodow(contract_date), isodow(contract_date) IN (6, 7)
        FROM (SELECT CAST(contract_date AS DATE) AS contract_date FROM stg)
        ON CONFLICT DO NOTHING""")
    con.unregister("stg")


def load_facts(con, df: pd.DataFrame, run_id: int) -> int:
    con.register("stg", df)
    con.execute("""
        INSERT OR REPLACE INTO fact_contract
            (contract_id, contract_number, org_inn, supplier_inn, product_code, date_key, quantity, unit_price,
             currency, amount, rate_uzs, amount_uzs, status, updated_at, loaded_at, run_id)
        SELECT contract_id, contract_number, org_inn, supplier_inn, product_code,
               CAST(strftime(CAST(contract_date AS DATE), '%Y%m%d') AS INTEGER),
               quantity, unit_price, currency, amount, rate_uzs, amount_uzs, status, updated_at,
               current_timestamp, ?
        FROM stg""", [run_id])
    con.unregister("stg")
    return len(df)


def load_quarantine(con, rejected: pd.DataFrame, run_id: int) -> int:
    if rejected.empty:
        return 0
    payload = rejected.drop(columns="reject_reason").apply(
        lambda r: r.to_json(date_format="iso", force_ascii=False), axis=1)
    q = pd.DataFrame({"run_id": run_id, "contract_id": rejected["contract_id"],
                      "reject_reason": rejected["reject_reason"], "payload": payload})
    con.register("stg_q", q)
    con.execute("""
        INSERT INTO quarantine_contract (run_id, contract_id, reject_reason, payload)
        SELECT run_id, contract_id, reject_reason, payload FROM stg_q""")
    con.unregister("stg_q")
    return len(q)
