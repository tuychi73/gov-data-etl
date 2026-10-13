from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from etl import load, pipeline, transform
from etl.config import Settings
from etl.extract import procurement


class FakeCbuSession:
    """cbu.uz o'rniga: har qanday sana uchun USD=12000, EUR=13500 qaytaradi."""

    def __init__(self):
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        data = [{"Ccy": "USD", "Rate": "12000", "Nominal": "1"},
                {"Ccy": "EUR", "Rate": "13500", "Nominal": "1"},
                {"Ccy": "RUB", "Rate": "150", "Nominal": "1"}]
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: data})()


@pytest.fixture(scope="module")
def api():
    from mock_api.app import app
    return TestClient(app)


@pytest.fixture
def settings(tmp_path):
    return Settings(api_base_url="http://testserver", api_key="demo-key", page_size=1000,
                    dwh_path=tmp_path / "dwh.duckdb", landing_dir=tmp_path / "landing")


def test_api_rejects_bad_key(api):
    assert api.get("/api/v1/contracts", headers={"X-API-Key": "wrong"}).status_code == 401


def test_pagination_reads_everything(api):
    pages = list(procurement.iter_contracts(api, "http://testserver", "demo-key", page_size=1000))
    total = api.get("/api/v1/contracts", headers={"X-API-Key": "demo-key"}).json()["total"]
    assert sum(len(p) for p in pages) == total
    assert len(pages) == -(-total // 1000)


def test_clean_rejects_bad_rows_and_dedupes():
    raw = pd.DataFrame([
        dict(contract_id=1, contract_number="A", org_inn="123456789", org_name=" Maktab  #1 ", region="Buxoro",
             supplier_inn="987654321", supplier_name="X", product_code="p", product_name="P", quantity=2,
             unit_price=10.0, currency="uzs", contract_date="2026-09-01", status="signed",
             updated_at="2026-09-01T10:00:00+00:00"),
        dict(contract_id=1, contract_number="A", org_inn="123456789", org_name="Maktab #1", region="Buxoro",
             supplier_inn="987654321", supplier_name="X", product_code="p", product_name="P", quantity=2,
             unit_price=10.0, currency="UZS", contract_date="2026-09-01", status="executed",
             updated_at="2026-09-03T10:00:00+00:00"),
        dict(contract_id=2, contract_number="B", org_inn="123456789", org_name="Maktab #1", region="Buxoro",
             supplier_inn="98765", supplier_name="Y", product_code="p", product_name="P", quantity=1,
             unit_price=-5.0, currency="UZS", contract_date=None, status="signed",
             updated_at="2026-09-01T10:00:00+00:00"),
    ])
    valid, rejected = transform.clean_contracts(raw)
    assert list(valid["contract_id"]) == [1]
    assert valid.loc[0, "status"] == "executed"            # eng oxirgi versiya
    assert valid.loc[0, "org_name"] == "Maktab #1"         # bo'shliqlar tozalangan
    assert valid.loc[0, "currency"] == "UZS"
    assert valid.loc[0, "amount"] == 20.0
    reasons = rejected.loc[0, "reject_reason"].split(";")
    assert {"invalid_supplier_inn", "missing_contract_date", "non_positive_price"} <= set(reasons)


def test_apply_rates_uses_previous_available_day():
    df = pd.DataFrame({"contract_id": [1, 2], "currency": ["USD", "UZS"], "amount": [10.0, 5.0],
                       "contract_date": [date(2026, 9, 6), date(2026, 9, 6)]})
    rates = pd.DataFrame({"rate_date": [date(2026, 9, 5)], "currency": ["USD"], "rate_uzs": [12000.0]})
    out, rejected = transform.apply_rates(df, rates)
    assert rejected.empty
    assert dict(zip(out["contract_id"], out["amount_uzs"])) == {1: 120000.0, 2: 5.0}


def test_full_run_then_incremental_is_idempotent(api, settings):
    cbu = FakeCbuSession()
    first = pipeline.run(settings, api_session=api, cbu_session=cbu)
    assert first.status == "success", first.dq
    assert first.loaded > 19_000 and first.rejected > 0
    assert (settings.landing_dir / f"contracts_run{first.run_id:05d}.parquet").exists()

    con = load.connect(settings.dwh_path)
    facts = con.execute("SELECT count(*) FROM fact_contract").fetchone()[0]
    con.close()

    # Ikkinchi run: yangi ma'lumot yo'q -> hech narsa o'zgarmaydi, kurslar qayta so'ralmaydi
    calls_before = cbu.calls
    second = pipeline.run(settings, api_session=api, cbu_session=cbu)
    assert second.extracted == 0 and cbu.calls == calls_before

    # Full refresh: hamma qayta yuklanadi, lekin dublikat paydo bo'lmaydi
    third = pipeline.run(settings, api_session=api, cbu_session=cbu, full_refresh=True)
    con = load.connect(settings.dwh_path)
    assert con.execute("SELECT count(*) FROM fact_contract").fetchone()[0] == facts == third.loaded
    assert con.execute("SELECT count(*) FROM mart_supplier_share").fetchone()[0] > 0
    con.close()
