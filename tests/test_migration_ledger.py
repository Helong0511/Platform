"""Migration ledger 原始记录验证；覆盖 dict 转换会丢失的冲突信息。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.db.migrations.manifest import Migration
from app.db.migrations.ledger import MigrationLedgerError, validate_ledger_rows
from app.db.migrations.planner import plan_migrations_from_ledger_rows


def _manifest(tmp_path: Path):
    entries = []
    for revision in ("20261110_first", "20261111_second", "20261112_third"):
        relative = f"sql/migrations/{revision}.sql"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"-- {revision}\n", encoding="utf-8")
        entries.append(
            Migration(
                revision=revision,
                path=relative,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return tuple(entries)


def _rows(entries, count=2):
    return [
        {
            "revision": item.revision,
            "checksum": item.sha256,
            "status": "applied",
            "execution_order": index,
        }
        for index, item in enumerate(entries[:count], start=1)
    ]


def test_ledger_rows_validate_before_mapping_and_plan_remaining(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = list(reversed(_rows(entries)))
    applied = validate_ledger_rows(
        rows, repository_root=tmp_path, migrations=entries
    )
    assert list(applied) == [entries[0].revision, entries[1].revision]
    plan = plan_migrations_from_ledger_rows(
        rows, repository_root=tmp_path, migrations=entries
    )
    assert [item.revision for item in plan] == [entries[2].revision]


def test_ledger_rejects_duplicate_revision_before_dict_overwrite(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows.append({**rows[0], "execution_order": 2})
    with pytest.raises(MigrationLedgerError, match="duplicate ledger revision"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_duplicate_execution_order(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries)
    rows[1]["execution_order"] = rows[0]["execution_order"]
    with pytest.raises(MigrationLedgerError, match="duplicate migration execution_order"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_execution_order_gap(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries)
    rows[1]["execution_order"] = 3
    with pytest.raises(MigrationLedgerError, match="contiguous sequence"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


@pytest.mark.parametrize("status", ["running", "failed", "APPLIED", None])
def test_ledger_rejects_non_applied_state_and_requires_manual_recovery(
    tmp_path: Path, status
):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows[0]["status"] = status
    with pytest.raises(MigrationLedgerError, match="manual DDL recovery is required"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_invalid_checksum_format(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows[0]["checksum"] = "A" * 64
    with pytest.raises(MigrationLedgerError, match="invalid ledger checksum"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_unknown_revision(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows[0]["revision"] = "20261109_unknown"
    with pytest.raises(MigrationLedgerError, match="unknown revision"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_checksum_drift(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows[0]["checksum"] = "0" * 64
    with pytest.raises(MigrationLedgerError, match="checksum drift"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)


def test_ledger_rejects_non_prefix_history(tmp_path: Path):
    entries = _manifest(tmp_path)
    rows = _rows(entries, count=1)
    rows[0]["revision"] = entries[1].revision
    rows[0]["checksum"] = entries[1].sha256
    with pytest.raises(MigrationLedgerError, match="contiguous manifest prefix"):
        validate_ledger_rows(rows, repository_root=tmp_path, migrations=entries)
