"""Davlat xaridlari axborot tizimining soddalashtirilgan REST API simulyatsiyasi.

Real integratsiyadagi holatlar takrorlanadi:
  * API kalit orqali autentifikatsiya (X-API-Key)
  * sahifalash (page / page_size)
  * inkremental yuklash (updated_since)
  * vaqtinchalik nosozliklar (503) - MOCK_FAIL_RATE orqali

Ishga tushirish:  uvicorn mock_api.app:app --port 8000
"""
from __future__ import annotations

import os
import random
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Query

from mock_api.data import generate_contracts

API_KEY = os.getenv("MOCK_API_KEY", "demo-key")
FAIL_RATE = float(os.getenv("MOCK_FAIL_RATE", "0"))

app = FastAPI(title="Mock Procurement Information System", version="1.0")
_CONTRACTS = generate_contracts(n=int(os.getenv("MOCK_CONTRACTS", "20000")))
_rng = random.Random(7)


@app.get("/api/v1/contracts")
def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
    updated_since: datetime | None = None,
    x_api_key: str | None = Header(default=None),
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if FAIL_RATE and _rng.random() < FAIL_RATE:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    items = _CONTRACTS
    if updated_since is not None:
        items = [r for r in items if datetime.fromisoformat(r["updated_at"]) > updated_since]

    start = (page - 1) * page_size
    chunk = items[start:start + page_size]
    return {
        "items": chunk,
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "has_next": start + page_size < len(items),
    }


@app.get("/health")
def health():
    return {"status": "ok", "contracts": len(_CONTRACTS)}
