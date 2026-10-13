from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_base_url: str = field(default_factory=lambda: os.getenv("PROCUREMENT_API_URL", "http://localhost:8000"))
    api_key: str = field(default_factory=lambda: os.getenv("PROCUREMENT_API_KEY", "demo-key"))
    page_size: int = field(default_factory=lambda: int(os.getenv("PAGE_SIZE", "1000")))
    cbu_base_url: str = field(default_factory=lambda: os.getenv("CBU_API_URL", "https://cbu.uz/uz/arkhiv-kursov-valyut/json"))
    dwh_path: Path = field(default_factory=lambda: Path(os.getenv("DWH_PATH", PROJECT_ROOT / "data" / "dwh.duckdb")))
    landing_dir: Path = field(default_factory=lambda: Path(os.getenv("LANDING_DIR", PROJECT_ROOT / "data" / "landing")))
