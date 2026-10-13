from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(retries: int = 5, backoff: float = 0.5) -> requests.Session:
    """429/5xx xatolarda eksponensial kutish bilan qayta urinadigan HTTP sessiya."""
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
