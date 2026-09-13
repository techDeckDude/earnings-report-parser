from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def _load_with_mem_db(contract_uri: str, mem_db):
    """Run loader.load() but redirect init_db to the in-memory connection."""
    with patch("loader.init_db", return_value=mem_db):
        from loader import load
        return load(contract_uri)


def test_load_valid_pltr_contract(mem_db):
    report_id = _load_with_mem_db(str(FIXTURES / "pltr_q2_2026.json"), mem_db)
    assert isinstance(report_id, int)
    row = mem_db.execute("SELECT ticker FROM companies WHERE ticker='PLTR'").fetchone()
    assert row is not None


def test_load_valid_mrvl_contract(mem_db):
    report_id = _load_with_mem_db(str(FIXTURES / "mrvl_q3_2024.json"), mem_db)
    assert isinstance(report_id, int)
    row = mem_db.execute("SELECT ticker FROM companies WHERE ticker='MRVL'").fetchone()
    assert row is not None


def test_load_is_idempotent(mem_db):
    _load_with_mem_db(str(FIXTURES / "pltr_q2_2026.json"), mem_db)
    _load_with_mem_db(str(FIXTURES / "pltr_q2_2026.json"), mem_db)
    count = mem_db.execute("SELECT COUNT(*) FROM earnings_reports").fetchone()[0]
    assert count == 1


def test_load_warns_on_unknown_schema_version(mem_db, tmp_path, capsys):
    contract = json.loads((FIXTURES / "pltr_q2_2026.json").read_text())
    contract["schema_version"] = "99.0"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(contract))
    _load_with_mem_db(str(bad), mem_db)
    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "99.0" in captured.out


def test_load_rejects_missing_required_field(mem_db, tmp_path):
    contract = json.loads((FIXTURES / "pltr_q2_2026.json").read_text())
    del contract["income_statement"]["revenue"]
    bad = tmp_path / "missing_field.json"
    bad.write_text(json.dumps(contract))
    with pytest.raises((SystemExit, ValidationError)):
        _load_with_mem_db(str(bad), mem_db)
