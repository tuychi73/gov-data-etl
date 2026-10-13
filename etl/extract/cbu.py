"""O'zbekiston Markaziy banki (cbu.uz) ochiq API'sidan valyuta kurslarini olish.

Endpoint: GET {base}/all/{YYYY-MM-DD}/  ->  [{"Ccy": "USD", "Rate": "11808.76", "Nominal": "1", "Date": "01.10.2026"}, ...]
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)

# Internet bo'lmaganda (--offline-rates) ishlatiladigan taxminiy kurslar
FALLBACK_RATES = {"USD": 12_000.0, "EUR": 13_500.0, "RUB": 150.0}


def _fetch_day(session, base_url: str, day: date, currencies: set[str]) -> list[dict]:
    resp = session.get(f"{base_url.rstrip('/')}/all/{day.isoformat()}/", timeout=20)
    resp.raise_for_status()
    rows = []
    for item in resp.json():
        if item["Ccy"] in currencies:
            rows.append({
                "rate_date": day,
                "currency": item["Ccy"],
                "rate_uzs": float(item["Rate"]) / float(item["Nominal"] or 1),
                "source": "cbu.uz",
            })
    return rows


def fetch_rates(session, base_url: str, days: Iterable[date], currencies: Iterable[str],
                max_workers: int = 6) -> pd.DataFrame:
    days = sorted(set(days))
    currencies = set(currencies)
    if not days or not currencies:
        return pd.DataFrame(columns=["rate_date", "currency", "rate_uzs", "source"])
    log.info("CBU: %s kun uchun kurslar olinmoqda", len(days))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        chunks = pool.map(lambda d: _fetch_day(session, base_url, d, currencies), days)
        rows = [r for chunk in chunks for r in chunk]
    return pd.DataFrame(rows)


def fallback_rates(days: Iterable[date], currencies: Iterable[str]) -> pd.DataFrame:
    rows = [{"rate_date": d, "currency": c, "rate_uzs": FALLBACK_RATES[c], "source": "fallback"}
            for d in sorted(set(days)) for c in set(currencies) if c in FALLBACK_RATES]
    return pd.DataFrame(rows, columns=["rate_date", "currency", "rate_uzs", "source"])
