"""Davlat xaridlari axborot tizimidan shartnomalarni sahifalab, inkremental olish."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime

log = logging.getLogger(__name__)


def iter_contracts(session, base_url: str, api_key: str, *, updated_since: datetime | None = None,
                   page_size: int = 1000, timeout: float = 30) -> Iterator[list[dict]]:
    """Har bir sahifadagi yozuvlarni qaytaradi. `session` - requests.Session yoki unga mos obyekt."""
    params: dict = {"page_size": page_size}
    if updated_since is not None:
        params["updated_since"] = updated_since.isoformat()

    page = 1
    while True:
        resp = session.get(f"{base_url.rstrip('/')}/api/v1/contracts",
                           params={**params, "page": page},
                           headers={"X-API-Key": api_key}, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        log.info("contracts page=%s items=%s total=%s", page, len(body["items"]), body["total"])
        if body["items"]:
            yield body["items"]
        if not body["has_next"]:
            break
        page += 1
