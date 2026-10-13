-- Tahliliy vitrinalar (data marts): auditorlar uchun tayyor ko'rinishlar

-- Tashkilotlar bo'yicha oylik xarajat
CREATE OR REPLACE VIEW mart_monthly_spend AS
SELECT o.org_inn,
       o.org_name,
       o.region,
       d.year,
       d.month,
       count(*)                     AS contracts,
       round(sum(f.amount_uzs), 0)  AS total_uzs
FROM fact_contract f
JOIN dim_organization o USING (org_inn)
JOIN dim_date d USING (date_key)
WHERE f.status <> 'cancelled'
GROUP BY ALL;

-- Har bir tashkilot xarajatida yetkazib beruvchining ulushi (konsentratsiya xavfi)
CREATE OR REPLACE VIEW mart_supplier_share AS
WITH s AS (
    SELECT org_inn, supplier_inn, sum(amount_uzs) AS spend
    FROM fact_contract
    WHERE status <> 'cancelled'
    GROUP BY ALL
)
SELECT s.org_inn,
       o.org_name,
       s.supplier_inn,
       sp.supplier_name,
       round(s.spend, 0)                                                AS spend_uzs,
       round(s.spend / sum(s.spend) OVER (PARTITION BY s.org_inn), 4)   AS share,
       rank() OVER (PARTITION BY s.org_inn ORDER BY s.spend DESC)       AS rnk
FROM s
JOIN dim_organization o USING (org_inn)
JOIN dim_supplier sp USING (supplier_inn);

-- Hududlar bo'yicha bir xil mahsulot narxining o'rtachadan og'ishi
CREATE OR REPLACE VIEW mart_price_by_region AS
WITH r AS (
    SELECT f.product_code,
           o.region,
           count(*)                                AS contracts,
           median(f.unit_price * f.rate_uzs)       AS median_price_uzs
    FROM fact_contract f
    JOIN dim_organization o USING (org_inn)
    GROUP BY f.product_code, o.region
)
SELECT r.product_code,
       p.product_name,
       r.region,
       r.contracts,
       round(r.median_price_uzs, 0)                                                         AS median_price_uzs,
       round(r.median_price_uzs / median(r.median_price_uzs) OVER (PARTITION BY r.product_code) - 1, 3) AS deviation
FROM r
JOIN dim_product p USING (product_code);
