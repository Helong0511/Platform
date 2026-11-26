"""按主键分批归因历史币种；默认只读，显式 --apply 才写入。"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections import Counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.third_party_currency import validate_iso_currency

logger = logging.getLogger("currency_attribution_backfill")
BATCH_SIZE_DEFAULT = 500
SOURCE_FIELDS = ("currency", "currency_code", "currencyCode")
TABLES = ("postback_conversions", "pending_postback_conversions")


def _payload_object(raw_data: Any) -> dict[str, Any]:
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, (bytes, bytearray)):
        raw_data = raw_data.decode("utf-8", errors="replace")
    if isinstance(raw_data, str):
        try:
            value = json.loads(raw_data)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def extract_currency(raw_data: Any) -> tuple[str, str]:
    """从已脱敏原始 payload 中恢复币种和精确字段来源；缺失时 USD 兜底。"""
    payload = _payload_object(raw_data)
    nested = payload.get("_payload")
    candidates = [payload]
    if isinstance(nested, dict):
        candidates.append(nested)
    for item in candidates:
        for field in SOURCE_FIELDS:
            value = item.get(field)
            if value is not None and str(value).strip():
                return str(value).strip().upper(), f"upstream_field:{field}"
    return "USD", "system_fallback_usd"


def _iso_status(currency: Any) -> str:
    try:
        validate_iso_currency(currency)
        return "valid"
    except (TypeError, ValueError):
        return "invalid"


async def _scan_postback_table(connection, table: str, *, batch_size: int, apply: bool) -> dict[str, Any]:
    if table not in TABLES:
        raise ValueError("unsupported table")
    last_id = 0
    scanned = 0
    updated = 0
    invalid: list[dict[str, Any]] = []
    invalid_count = 0
    sources: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    while True:
        result = await connection.execute(
            text(
                f"SELECT id, currency, currency_source, raw_data FROM {table} "
                "WHERE id > :last_id ORDER BY id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": batch_size},
        )
        rows = result.mappings().all()
        result.close()
        if not rows:
            break
        last_id = int(rows[-1]["id"])
        scanned += len(rows)
        updates = []
        for row in rows:
            current_source = row["currency_source"] or "system_fallback_usd"
            current_currency = str(row["currency"] or "USD").strip().upper() or "USD"
            if current_source == "system_fallback_usd":
                recovered_currency, recovered_source = extract_currency(row["raw_data"])
                if recovered_source != "system_fallback_usd":
                    current_currency, current_source = recovered_currency, recovered_source
                else:
                    current_currency, current_source = "USD", "system_fallback_usd"
            status = _iso_status(current_currency)
            currencies[current_currency] += 1
            sources[current_source] += 1
            if status != "valid":
                invalid_count += 1
                if len(invalid) < 200:
                    invalid.append({"id": int(row["id"]), "currency": current_currency, "source": current_source})
            if (
                apply
                and (row["currency"] != current_currency or row["currency_source"] != current_source)
                and len(current_currency) <= 10
            ):
                updates.append(
                    {"id": int(row["id"]), "currency": current_currency, "currency_source": current_source}
                )
        if updates:
            await connection.execute(
                text(
                    f"UPDATE {table} SET currency = :currency, currency_source = :currency_source "
                    "WHERE id = :id"
                ),
                updates,
            )
            await connection.commit()
            updated += len(updates)
    return {
        "table": table,
        "scanned": scanned,
        "updated": updated,
        "currencies": dict(sorted(currencies.items())),
        "sources": dict(sorted(sources.items())),
        "invalid_count": invalid_count,
        "invalid_sample": invalid,
    }


async def _scan_deduction_logs(connection, *, batch_size: int, apply: bool) -> dict[str, Any]:
    last_id = 0
    scanned = 0
    updated = 0
    invalid: list[dict[str, Any]] = []
    invalid_count = 0
    sources: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    while True:
        result = await connection.execute(
            text(
                "SELECT d.id, d.currency, d.currency_source, p.currency AS conversion_currency, "
                "p.currency_source AS conversion_currency_source "
                "FROM conversion_deduction_logs d "
                "LEFT JOIN postback_conversions p ON p.id = d.conversion_id "
                "WHERE d.id > :last_id ORDER BY d.id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": batch_size},
        )
        rows = result.mappings().all()
        result.close()
        if not rows:
            break
        last_id = int(rows[-1]["id"])
        scanned += len(rows)
        updates = []
        for row in rows:
            currency = str(row["currency"] or "USD").strip().upper() or "USD"
            source = row["currency_source"] or "system_fallback_usd"
            if source == "system_fallback_usd" and row["conversion_currency"]:
                currency = str(row["conversion_currency"]).strip().upper()
                source = row["conversion_currency_source"] or "legacy_unknown"
            status = _iso_status(currency)
            currencies[currency] += 1
            sources[source] += 1
            if status != "valid":
                invalid_count += 1
                if len(invalid) < 200:
                    invalid.append({"id": int(row["id"]), "currency": currency, "source": source})
            if apply and (row["currency"] != currency or row["currency_source"] != source):
                updates.append({"id": int(row["id"]), "currency": currency, "currency_source": source})
        if updates:
            await connection.execute(
                text(
                    "UPDATE conversion_deduction_logs SET currency = :currency, "
                    "currency_source = :currency_source WHERE id = :id"
                ),
                updates,
            )
            await connection.commit()
            updated += len(updates)
    return {
        "table": "conversion_deduction_logs",
        "scanned": scanned,
        "updated": updated,
        "currencies": dict(sorted(currencies.items())),
        "sources": dict(sorted(sources.items())),
        "invalid_count": invalid_count,
        "invalid_sample": invalid,
    }


async def _scan_report_logs(connection, *, batch_size: int, apply: bool) -> dict[str, Any]:
    last_id = 0
    scanned = 0
    updated = 0
    invalid: list[dict[str, Any]] = []
    invalid_count = 0
    sources: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    while True:
        result = await connection.execute(
            text(
                "SELECT id, currency, currency_source FROM third_party_report_logs "
                "WHERE id > :last_id ORDER BY id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": batch_size},
        )
        rows = result.mappings().all()
        result.close()
        if not rows:
            break
        last_id = int(rows[-1]["id"])
        scanned += len(rows)
        updates = []
        for row in rows:
            currency = str(row["currency"] or "").strip().upper()
            source = row["currency_source"]
            if not currency:
                currency, source = "USD", "system_fallback_usd"
            elif not source:
                source = "legacy_unknown"
            status = _iso_status(currency)
            currencies[currency] += 1
            sources[source] += 1
            if status != "valid":
                invalid_count += 1
                if len(invalid) < 200:
                    invalid.append({"id": int(row["id"]), "currency": currency, "source": source})
            if apply and (row["currency"] != currency or row["currency_source"] != source):
                updates.append({"id": int(row["id"]), "currency": currency, "currency_source": source})
        if updates:
            await connection.execute(
                text(
                    "UPDATE third_party_report_logs SET currency = :currency, "
                    "currency_source = :currency_source WHERE id = :id"
                ),
                updates,
            )
            await connection.commit()
            updated += len(updates)
    return {
        "table": "third_party_report_logs",
        "scanned": scanned,
        "updated": updated,
        "currencies": dict(sorted(currencies.items())),
        "sources": dict(sorted(sources.items())),
        "invalid_count": invalid_count,
        "invalid_sample": invalid,
    }


async def run_backfill(*, apply: bool, batch_size: int) -> list[dict[str, Any]]:
    dsn = os.getenv("MIGRATION_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("必须设置独立 MIGRATION_DATABASE_URL；不会回退到应用 DSN")
    if not dsn.startswith(("mysql+asyncmy://", "mysql+aiomysql://")):
        raise RuntimeError("MIGRATION_DATABASE_URL 必须使用 MySQL async 驱动")
    engine = create_async_engine(dsn, pool_pre_ping=True, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT VERSION()"))
            if not str(version or "").startswith("8."):
                raise RuntimeError("币种归因回填仅允许在 MySQL 8.x 执行")
            results = []
            for table in TABLES:
                results.append(await _scan_postback_table(connection, table, batch_size=batch_size, apply=apply))
            results.append(await _scan_deduction_logs(connection, batch_size=batch_size, apply=apply))
            results.append(await _scan_report_logs(connection, batch_size=batch_size, apply=apply))
            # 斗篷配置量小，统一扫描并验证；空值在 schema migration 中已兜底 USD。
            result = await connection.execute(
                text("SELECT id, report_currency, report_currency_source, load_report_currency, load_report_currency_source, postback_report_currency, postback_report_currency_source FROM cloak_configs ORDER BY id")
            )
            rows = result.mappings().all()
            result.close()
            invalid_configs = []
            invalid_config_count = 0
            config_sources: Counter[str] = Counter()
            for row in rows:
                for field in ("report_currency", "load_report_currency", "postback_report_currency"):
                    value = str(row[field] or "USD").strip().upper() or "USD"
                    source = row[f"{field}_source"] or "legacy_unknown"
                    config_sources[source] += 1
                    if _iso_status(value) != "valid":
                        invalid_config_count += 1
                        if len(invalid_configs) < 200:
                            invalid_configs.append({"id": int(row["id"]), "field": field, "currency": value, "source": source})
            results.append({"table": "cloak_configs", "scanned": len(rows), "sources": dict(sorted(config_sources.items())), "invalid_count": invalid_config_count, "invalid_sample": invalid_configs})
            return results
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Postback/第三方币种历史来源归因与 ISO 4217 审计")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--apply", action="store_true", help="执行分批写入；默认只读 dry-run")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000:
        parser.error("--batch-size 必须在 1 到 5000 之间")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = asyncio.run(run_backfill(apply=args.apply, batch_size=args.batch_size))
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
