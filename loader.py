"""
loader.py — Load a normalized contract JSON into the database.

Usage:
    python loader.py s3://financial-statements/PLTR/10-Q/FY2026Q2.json
    python loader.py path/to/local/contract.json

The contract is a serialized EarningsReport (schema_version 1.0).
Reads from S3 when the URI starts with s3://, otherwise from a local file.
Uses Postgres when DB_HOST is set, SQLite otherwise.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from pydantic import ValidationError

from models import EarningsReport
from db import init_db, upsert_report


SUPPORTED_VERSIONS = {"1.0"}


def _read_s3(uri: str) -> dict:
    import boto3
    _, rest = uri.split("s3://", 1)
    bucket, key = rest.split("/", 1)
    obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())


def _read_local(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load(contract_uri: str) -> int:
    """
    Read a contract from S3 or local disk, validate it, and upsert into the DB.
    Returns the report_id.
    """
    print(f"[1/3] Reading contract: {contract_uri}")
    if contract_uri.startswith("s3://"):
        data = _read_s3(contract_uri)
    else:
        data = _read_local(contract_uri)

    version = data.get("schema_version", "unknown")
    if version not in SUPPORTED_VERSIONS:
        print(f"      WARNING: schema_version '{version}' not in {SUPPORTED_VERSIONS}. Proceeding anyway.")
    print(f"      schema_version={version}")

    print("[2/3] Validating contract...")
    try:
        report = EarningsReport.model_validate(data)
    except ValidationError as e:
        print(f"ERROR: Contract validation failed:\n{e}", file=sys.stderr)
        sys.exit(1)
    print(f"      Valid — {report.ticker} {report.period}")

    print("[3/3] Writing to database...")
    conn = init_db()
    report_id = upsert_report(conn, report)
    print(f"      Done. report_id={report_id}")
    return report_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python loader.py <s3://bucket/key.json | path/to/contract.json>")
        sys.exit(1)
    load(sys.argv[1])
