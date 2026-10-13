"""CLI:
    python -m etl run [--full-refresh] [--offline-rates]
    python -m etl report
"""
from __future__ import annotations

import argparse
import logging
import sys

from etl import load, pipeline
from etl.config import Settings


def _print_df(title: str, df) -> None:
    print(f"\n=== {title} ===")
    print(df.to_string(index=False) if not df.empty else "(bo'sh)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="etl", description="Davlat xaridlari ETL pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="ETL'ni ishga tushirish")
    p_run.add_argument("--full-refresh", action="store_true", help="watermark'ni e'tiborsiz qoldirib, hammasini qayta yuklash")
    p_run.add_argument("--offline-rates", action="store_true", help="cbu.uz o'rniga taxminiy kurslardan foydalanish")
    sub.add_parser("report", help="Omborda nima borligini ko'rsatish")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()

    if args.cmd == "run":
        res = pipeline.run(settings, full_refresh=args.full_refresh, offline_rates=args.offline_rates)
        print(f"\nrun_id={res.run_id} status={res.status} extracted={res.extracted} "
              f"loaded={res.loaded} rejected={res.rejected} watermark={res.watermark}")
        for r in res.dq:
            print(f"  [{'OK ' if r['passed'] else 'FAIL'}] {r['check']:<30} {r['severity']:<5} failed_rows={r['failed_rows']}")
        return 0 if res.status == "success" else 1

    con = load.connect(settings.dwh_path)
    load.init_schema(con)
    _print_df("ETL run'lar", con.execute(
        "SELECT run_id, status, extracted, loaded, rejected, watermark FROM etl_run_log ORDER BY run_id DESC LIMIT 5").df())
    _print_df("Karantin sabablari", con.execute(
        "SELECT reject_reason, count(*) n FROM quarantine_contract GROUP BY 1 ORDER BY n DESC").df())
    _print_df("Eng ko'p xarajat qilgan 10 tashkilot", con.execute(
        "SELECT org_name, region, CAST(sum(total_uzs) AS BIGINT) total_uzs, CAST(sum(contracts) AS INTEGER) contracts "
        "FROM mart_monthly_spend GROUP BY ALL ORDER BY total_uzs DESC LIMIT 10").df())
    _print_df("Yetkazib beruvchi ulushi > 30% (konsentratsiya)", con.execute(
        "SELECT org_name, supplier_name, CAST(spend_uzs AS BIGINT) spend_uzs, share FROM mart_supplier_share "
        "WHERE share > 0.3 ORDER BY share DESC LIMIT 10").df())
    _print_df("Hududiy narx og'ishi > 15%", con.execute(
        "SELECT product_name, region, median_price_uzs, deviation FROM mart_price_by_region "
        "WHERE abs(deviation) > 0.15 ORDER BY abs(deviation) DESC LIMIT 10").df())
    return 0


if __name__ == "__main__":
    sys.exit(main())
