"""ETL orkestratsiyasi: Extract -> Landing (raw) -> Transform -> Load -> Data Quality."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from etl import load, quality, transform
from etl.config import Settings
from etl.extract import cbu, procurement
from etl.extract.http import build_session

log = logging.getLogger(__name__)
WATERMARK_KEY = "contracts_updated_at_watermark"


@dataclass
class RunResult:
    run_id: int
    status: str
    extracted: int = 0
    loaded: int = 0
    rejected: int = 0
    watermark: datetime | None = None
    dq: list[dict] = field(default_factory=list)


def run(settings: Settings, *, full_refresh: bool = False, offline_rates: bool = False,
        api_session=None, cbu_session=None, con=None) -> RunResult:
    con = con or load.connect(settings.dwh_path)
    load.init_schema(con)
    run_id = load.start_run(con)
    try:
        return _run(con, run_id, settings, full_refresh, offline_rates,
                    api_session or build_session(), cbu_session or build_session())
    except Exception as exc:
        load.finish_run(con, run_id, "failed", message=f"{type(exc).__name__}: {exc}"[:500])
        raise


def _run(con, run_id, settings, full_refresh, offline_rates, api_session, cbu_session) -> RunResult:
    # 1. EXTRACT (inkremental: faqat oxirgi muvaffaqiyatli yuklashdan keyin o'zgarganlar)
    wm_raw = None if full_refresh else load.get_state(con, WATERMARK_KEY)
    watermark = datetime.fromisoformat(wm_raw) if wm_raw else None
    log.info("run_id=%s watermark=%s", run_id, watermark)

    pages = procurement.iter_contracts(api_session, settings.api_base_url, settings.api_key,
                                       updated_since=watermark, page_size=settings.page_size)
    raw = pd.DataFrame([row for page in pages for row in page])
    if raw.empty:
        load.finish_run(con, run_id, "success", watermark=watermark, message="no new data")
        return RunResult(run_id, "success", watermark=watermark)

    # 2. LANDING: xom ma'lumot o'zgarishsiz saqlanadi (qayta ishlash va audit izi uchun)
    settings.landing_dir.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(settings.landing_dir / f"contracts_run{run_id:05d}.parquet", index=False)

    # 3. TRANSFORM
    valid, rejected = transform.clean_contracts(raw)
    fx_needed = valid.loc[valid["currency"] != "UZS", ["contract_date", "currency"]].drop_duplicates()
    missing = [(d, c) for d, c in fx_needed.itertuples(index=False) if (d, c) not in load.known_rate_keys(con)]
    if missing:
        days, currencies = {d for d, _ in missing}, {c for _, c in missing}
        rates = (cbu.fallback_rates(days, currencies) if offline_rates
                 else cbu.fetch_rates(cbu_session, settings.cbu_base_url, days, currencies))
        load.load_rates(con, rates)
    valid, no_rate = transform.apply_rates(valid, load.all_rates(con))
    rejected = pd.concat([rejected, no_rate], ignore_index=True)

    # 4. LOAD (bitta tranzaksiyada: yarim yuklangan holat qolmaydi)
    con.execute("BEGIN TRANSACTION")
    try:
        load.load_dimensions(con, valid)
        loaded = load.load_facts(con, valid, run_id)
        n_rejected = load.load_quarantine(con, rejected, run_id)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    # 5. DATA QUALITY
    dq = quality.run_checks(con, run_id)
    errors = [r for r in dq if not r["passed"] and r["severity"] == "error"]
    status = "dq_failed" if errors else "success"

    # Watermark faqat muvaffaqiyatli run'dan keyin suriladi
    new_wm = pd.to_datetime(raw["updated_at"], utc=True, errors="coerce").max().to_pydatetime()
    if status == "success":
        load.set_state(con, WATERMARK_KEY, new_wm.isoformat())
    load.finish_run(con, run_id, status, extracted=len(raw), loaded=loaded, rejected=n_rejected,
                    watermark=new_wm, message=", ".join(e["check"] for e in errors) or None)
    log.info("run_id=%s status=%s extracted=%s loaded=%s rejected=%s", run_id, status, len(raw), loaded, n_rejected)
    return RunResult(run_id, status, len(raw), loaded, n_rejected, new_wm, dq)
