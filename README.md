# gov-data-etl — davlat xaridlari ma'lumotlari uchun ETL pipeline

Davlat organining axborot tizimidan (REST API) shartnomalarni **inkremental** olib, tozalab,
Markaziy bank kurslari bo'yicha so'mga keltirib, **star schema** ko'rinishidagi ma'lumotlar omboriga
yuklaydigan va har bir yuklashdan keyin **ma'lumotlar sifatini** tekshiradigan pipeline.

```
 Axborot tizimi API ──┐                       ┌─► dim_organization ─┐
 (sahifalash, API-kalit,│   Landing (Parquet)  ├─► dim_supplier      │
  vaqtinchalik 503)    ├─► xom ma'lumot ──► Transform ─┤─► dim_product       ├─► mart_* (tahliliy view'lar)
 cbu.uz kurslar API ───┘    (audit izi)        ├─► dim_date          │
                                               ├─► fact_contract ────┘
                                               └─► quarantine_contract (rad etilganlar + sababi)
                                    Data Quality ──► dq_check_result,  etl_run_log,  etl_state (watermark)
```

## Nimalar amalga oshirilgan

| Bosqich | Yechim |
|---|---|
| **Extract** | `requests` + `urllib3.Retry`: 429/5xx da eksponensial kutish bilan qayta urinish; sahifalab o'qish; API-kalit; `updated_since` bo'yicha **inkremental** olish (watermark) |
| **Tashqi API** | O'zbekiston Markaziy banki ochiq API'si (`cbu.uz`) — har bir sana uchun kurslar parallel (`ThreadPoolExecutor`) olinadi va omborda keshlanadi |
| **Landing** | Xom ma'lumot o'zgarishsiz Parquet'ga saqlanadi (qayta ishlash va audit izi uchun) |
| **Transform** | Matnni normallashtirish, INN validatsiyasi (9 raqam), bo'sh sana / manfiy narx / noma'lum valyutani aniqlash, **dublikatlarni** eng oxirgi versiya bo'yicha olib tashlash, bir INN uchun turlicha yozilgan nomlarni yagona ko'rinishga keltirish, kursni `merge_asof` bilan (sana yoki undan oldingi eng yaqin kun) qo'llash |
| **Load** | DuckDB'da star schema; barcha yuklashlar **idempotent** (upsert) va **bitta tranzaksiyada** |
| **Karantin** | Rad etilgan yozuvlar o'chirib yuborilmaydi — sababi va asl JSON'i bilan saqlanadi |
| **Data Quality** | 10 ta tekshiruv: PK unikalligi, NOT NULL, FK yaxlitligi, `amount = qty × price`, kelajakdagi sana, karantin ulushi va h.k. `error` darajasidagi xato bo'lsa run `dq_failed` bo'ladi va watermark surilmaydi |
| **Marts** | Oylik xarajat, yetkazib beruvchi ulushi (konsentratsiya xavfi), hududlar bo'yicha narx og'ishi |

## Natija (haqiqiy run)

```
run_id=1 status=success extracted=20200 loaded=19635 rejected=368
  [OK ] fact_pk_unique / fact_required_not_null / fk_organization / fk_supplier / fk_date / ...  (10/10)

Karantin sabablari:  invalid_supplier_inn 203 · missing_contract_date 99 · non_positive_price 65 · ...
run_id=2 status=success extracted=0   # inkremental: yangi ma'lumot yo'q -> hech narsa qayta yuklanmaydi
```
20 200 ta yozuvdan 197 tasi dublikat bo'lib birlashtirildi, 368 tasi karantinga tushdi.
Mock API'da 5% so'rov ataylab 503 qaytarganiga qaramay barcha ma'lumot olindi.

## Ishga tushirish

```bat
python -m venv .venv && .venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 1-terminal: axborot tizimi simulyatsiyasi (5% so'rov ataylab xato qaytaradi)
set MOCK_FAIL_RATE=0.05
uvicorn mock_api.app:app --port 8000

# 2-terminal
python -m etl run                 # birinchi run: hamma ma'lumot + cbu.uz kurslari
python -m etl run                 # inkremental: faqat yangi/o'zgargan yozuvlar
python -m etl run --full-refresh  # hammasini qayta yuklash (dublikat paydo bo'lmaydi)
python -m etl report              # ombordagi natijalar
pytest                            # testlar
```
Internet bo'lmasa: `python -m etl run --offline-rates` (taxminiy kurslar, DQ ogohlantirish beradi).

## Loyiha tuzilmasi

```
etl/extract/   procurement.py (sahifalash, inkremental) · cbu.py (Markaziy bank API) · http.py (retry)
etl/transform.py   tozalash, validatsiya, valyuta konvertatsiyasi
etl/load.py        DuckDB'ga upsert, run log, watermark
etl/quality.py     data quality tekshiruvlari
etl/pipeline.py    orkestratsiya
sql/schema.sql     star schema    sql/marts.sql   tahliliy view'lar
mock_api/          FastAPI'da axborot tizimi simulyatsiyasi (sintetik, ataylab "iflos" ma'lumot)
tests/             pytest: pagination, tozalash, kurs qo'llash, idempotentlik
```

## Dizayn qarorlari

- **Nega DuckDB?** Serversiz, ustunli (columnar) analitik ombor — lokal ishlab chiqish uchun qulay.
  SQL'i PostgreSQL'ga yaqin; prod muhitda `load.py` PostgreSQL/ClickHouse'ga almashtiriladi.
- **Nega FK cheklovlari yo'q?** Katta hajmda yuklash tezligi uchun; yaxlitlik DQ tekshiruvlari orqali nazorat qilinadi.
- **Watermark faqat muvaffaqiyatli run'dan keyin suriladi** — xato bo'lsa keyingi run o'sha joydan davom etadi.
- **Cheklov:** `updated_at > watermark` sharti bir xil vaqt belgisi bilan kechikib kelgan yozuvni o'tkazib yuborishi mumkin;
  prod'da kichik "overlap" oynasi (masalan, watermark − 5 daqiqa) va upsert bilan hal qilinadi.

> Mock API'dagi ma'lumotlar sintetik. Markaziy bank kurslari — haqiqiy (`cbu.uz` ochiq API).
