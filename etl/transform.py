"""Tozalash, validatsiya va valyutani so'mga keltirish (Transform bosqichi)."""
from __future__ import annotations

import pandas as pd

ALLOWED_CURRENCIES = {"UZS", "USD", "EUR", "RUB"}
TEXT_COLUMNS = ["contract_number", "org_inn", "org_name", "region", "supplier_inn",
                "supplier_name", "product_code", "product_name", "currency", "status"]
INN_PATTERN = r"^\d{9}$"


def _normalize_text(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)


def _canonical_name(df: pd.DataFrame, key: str, name: str) -> pd.Series:
    """Bir INN uchun turlicha yozilgan nomlardan eng ko'p uchraydiganini tanlaydi."""
    mode = (df.groupby([key, name]).size().reset_index(name="n")
              .sort_values([key, "n"], ascending=[True, False])
              .drop_duplicates(key).set_index(key)[name])
    return df[key].map(mode)


def clean_contracts(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(valid, rejected) qaytaradi. Rad etilgan yozuvlar sababi bilan karantinga tushadi."""
    df = raw.copy()
    for col in TEXT_COLUMNS:
        df[col] = _normalize_text(df[col])
    df["currency"] = df["currency"].str.upper()
    df["contract_date"] = pd.to_datetime(df["contract_date"], errors="coerce").dt.date
    df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True, errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

    checks = {
        "invalid_org_inn": ~df["org_inn"].fillna("").str.match(INN_PATTERN),
        "invalid_supplier_inn": ~df["supplier_inn"].fillna("").str.match(INN_PATTERN),
        "missing_contract_date": df["contract_date"].isna(),
        "missing_updated_at": df["updated_at"].isna(),
        "non_positive_quantity": ~(df["quantity"] > 0),
        "non_positive_price": ~(df["unit_price"] > 0),
        "unknown_currency": ~df["currency"].isin(ALLOWED_CURRENCIES),
    }
    reasons = pd.Series("", index=df.index)
    for name, mask in checks.items():
        reasons = reasons.where(~mask, reasons + name + ";")

    bad = reasons != ""
    rejected = df[bad].assign(reject_reason=reasons[bad].str.rstrip(";"))
    valid = df[~bad].copy()

    # Bir shartnoma bir necha marta kelsa - eng oxirgi versiyasi qoladi
    valid = (valid.sort_values(["contract_id", "updated_at"])
                  .drop_duplicates("contract_id", keep="last"))
    valid["org_name"] = _canonical_name(valid, "org_inn", "org_name")
    valid["supplier_name"] = _canonical_name(valid, "supplier_inn", "supplier_name")
    valid["amount"] = (valid["quantity"] * valid["unit_price"]).round(2)
    return valid.reset_index(drop=True), rejected.reset_index(drop=True)


def apply_rates(df: pd.DataFrame, rates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Har bir shartnoma summasini shartnoma sanasidagi (yoki undan oldingi eng yaqin) kurs bo'yicha so'mga o'giradi."""
    df = df.copy()
    df["_date"] = pd.to_datetime(df["contract_date"]).astype("datetime64[ns]")
    uzs = df[df["currency"] == "UZS"].assign(rate_uzs=1.0)
    fx = df[df["currency"] != "UZS"]

    if not fx.empty:
        r = rates.copy()
        r["_date"] = pd.to_datetime(r["rate_date"]).astype("datetime64[ns]")
        r["currency"] = r["currency"].astype(object)
        fx = fx.assign(currency=fx["currency"].astype(object))
        fx = pd.merge_asof(fx.sort_values("_date"), r[["_date", "currency", "rate_uzs"]].sort_values("_date"),
                           on="_date", by="currency", direction="backward")
    out = pd.concat([uzs, fx], ignore_index=True)

    no_rate = out["rate_uzs"].isna()
    rejected = out[no_rate].assign(reject_reason="missing_fx_rate").drop(columns=["_date", "rate_uzs"])
    out = out[~no_rate].copy()
    out["amount_uzs"] = (out["amount"] * out["rate_uzs"]).round(2)
    return out.drop(columns="_date").reset_index(drop=True), rejected.reset_index(drop=True)
