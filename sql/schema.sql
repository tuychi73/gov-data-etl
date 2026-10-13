-- Ma'lumotlar ombori: "yulduz" (star schema) modeli
-- FK cheklovlari ataylab qo'yilmagan: yuklash tezligi uchun, yaxlitlik esa data quality tekshiruvlarida nazorat qilinadi.

CREATE TABLE IF NOT EXISTS dim_organization (
    org_inn     VARCHAR PRIMARY KEY,
    org_name    VARCHAR NOT NULL,
    region      VARCHAR,
    updated_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS dim_supplier (
    supplier_inn  VARCHAR PRIMARY KEY,
    supplier_name VARCHAR NOT NULL,
    first_seen    DATE,
    updated_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_code VARCHAR PRIMARY KEY,
    product_name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,   -- YYYYMMDD
    full_date    DATE NOT NULL,
    year         SMALLINT,
    quarter      SMALLINT,
    month        SMALLINT,
    day_of_week  SMALLINT,              -- 1 = dushanba ... 7 = yakshanba
    is_weekend   BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_currency_rate (
    rate_date DATE,
    currency  VARCHAR,
    rate_uzs  DOUBLE NOT NULL,
    source    VARCHAR,
    PRIMARY KEY (rate_date, currency)
);

CREATE TABLE IF NOT EXISTS fact_contract (
    contract_id     BIGINT PRIMARY KEY,
    contract_number VARCHAR NOT NULL,
    org_inn         VARCHAR NOT NULL,
    supplier_inn    VARCHAR NOT NULL,
    product_code    VARCHAR NOT NULL,
    date_key        INTEGER NOT NULL,
    quantity        DOUBLE,
    unit_price      DOUBLE,
    currency        VARCHAR,
    amount          DOUBLE,
    rate_uzs        DOUBLE,
    amount_uzs      DOUBLE,
    status          VARCHAR,
    updated_at      TIMESTAMPTZ,
    loaded_at       TIMESTAMPTZ DEFAULT current_timestamp,
    run_id          INTEGER
);

-- Rad etilgan yozuvlar (karantin): sababi bilan saqlanadi, keyin tahlil qilinadi
CREATE TABLE IF NOT EXISTS quarantine_contract (
    run_id        INTEGER,
    contract_id   BIGINT,
    reject_reason VARCHAR,
    payload       JSON,
    rejected_at   TIMESTAMPTZ DEFAULT current_timestamp
);

-- Texnik jadvallar
CREATE SEQUENCE IF NOT EXISTS seq_run_id START 1;

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id        INTEGER PRIMARY KEY,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    status        VARCHAR,
    extracted     INTEGER,
    loaded        INTEGER,
    rejected      INTEGER,
    watermark     TIMESTAMPTZ,
    message       VARCHAR
);

CREATE TABLE IF NOT EXISTS etl_state (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

CREATE TABLE IF NOT EXISTS dq_check_result (
    run_id      INTEGER,
    check_name  VARCHAR,
    severity    VARCHAR,
    failed_rows BIGINT,
    passed      BOOLEAN,
    checked_at  TIMESTAMPTZ DEFAULT current_timestamp
);
