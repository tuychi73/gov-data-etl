"""Mock davlat xaridlari axborot tizimi uchun sintetik ma'lumotlar.

Real tizimlardagidek "iflos" yozuvlar ataylab qo'shiladi:
dublikatlar, noto'g'ri INN, bo'sh sana, manfiy summa, ortiqcha bo'shliqlar.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

REGIONS = [
    "Toshkent sh.", "Toshkent vil.", "Samarqand", "Buxoro", "Farg'ona",
    "Andijon", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm",
    "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston",
]

PRODUCTS = [
    ("30.02.11", "Noutbuk", 9_500_000),
    ("30.02.12", "Monitor", 2_800_000),
    ("30.02.15", "Printer", 3_200_000),
    ("17.12.14", "Ofis qog'ozi (pachka)", 55_000),
    ("31.01.11", "Ofis stoli", 1_900_000),
    ("31.01.12", "Ofis kreslosi", 1_400_000),
    ("28.25.12", "Konditsioner", 6_700_000),
    ("19.20.21", "Benzin AI-92 (litr)", 11_000),
    ("62.01.11", "Dasturiy ta'minot litsenziyasi", 4_500_000),
    ("43.21.10", "Elektr montaj ishlari", 25_000_000),
]

STATUSES = ["signed", "signed", "signed", "executed", "cancelled"]


def _inn(rng: random.Random) -> str:
    return str(rng.randint(200_000_000, 309_999_999))


def generate_contracts(n: int = 20_000, days: int = 120, seed: int = 42,
                       today: date | None = None) -> list[dict]:
    rng = random.Random(seed)
    today = today or date(2026, 10, 1)
    orgs = [{"inn": _inn(rng), "name": f"{rng.choice(['Hokimiyat', 'Shifoxona', 'Maktab', 'Vazirlik boshqarmasi', 'Kollej'])} #{i}",
             "region": rng.choice(REGIONS)} for i in range(1, 151)]
    suppliers = [{"inn": _inn(rng), "name": f"\"{rng.choice(['Mega', 'Smart', 'Global', 'Asia', 'Nur', 'Baraka'])} "
                                            f"{rng.choice(['Trade', 'Servis', 'Group', 'Tech', 'Invest'])}\" MChJ #{i}"}
                 for i in range(1, 401)]

    rows: list[dict] = []
    for i in range(1, n + 1):
        org = rng.choice(orgs)
        sup = rng.choice(suppliers)
        code, pname, base_price = rng.choice(PRODUCTS)
        currency = rng.choices(["UZS", "USD", "EUR"], weights=[85, 12, 3])[0]
        price_uzs = base_price * rng.uniform(0.8, 1.25)
        unit_price = price_uzs if currency == "UZS" else price_uzs / (12_000 if currency == "USD" else 13_500)
        d = today - timedelta(days=rng.randint(0, days - 1))
        updated = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
            hours=rng.randint(8, 18), minutes=rng.randint(0, 59), days=rng.choice([0, 0, 0, 1, 3]))
        rows.append({
            "contract_id": i,
            "contract_number": f"{d.year}-{org['inn'][-4:]}-{i:06d}",
            "org_inn": org["inn"], "org_name": org["name"], "region": org["region"],
            "supplier_inn": sup["inn"], "supplier_name": sup["name"],
            "product_code": code, "product_name": pname,
            "quantity": rng.choice([1, 1, 2, 3, 5, 10, 20, 50, 100]),
            "unit_price": round(unit_price, 2),
            "currency": currency,
            "contract_date": d.isoformat(),
            "status": rng.choice(STATUSES),
            "updated_at": updated.isoformat(),
        })

    # --- Ataylab qo'shilgan sifatsiz yozuvlar (~3%) ---
    for row in rng.sample(rows, k=n // 100):
        row["supplier_inn"] = row["supplier_inn"][:7]            # noto'g'ri INN
    for row in rng.sample(rows, k=n // 200):
        row["contract_date"] = None                               # bo'sh sana
    for row in rng.sample(rows, k=n // 300):
        row["unit_price"] = -abs(row["unit_price"])               # manfiy narx
    for row in rng.sample(rows, k=n // 100):
        row["org_name"] = f"  {row['org_name'].upper()}  "        # format xatosi
        row["currency"] = row["currency"].lower()
    # Bir xil shartnoma keyinroq yangilangan holda qayta keladi (dublikat)
    for row in rng.sample(rows, k=n // 100):
        dup = dict(row)
        dup["status"] = "executed"
        dup["updated_at"] = (datetime.fromisoformat(row["updated_at"]) + timedelta(days=2)).isoformat()
        rows.append(dup)

    rows.sort(key=lambda r: (r["updated_at"], r["contract_id"]))
    return rows
