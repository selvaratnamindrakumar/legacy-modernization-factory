"""Generate deterministic, synthetic records for sandbox load testing.

Examples:
  python scripts/populate_test_data.py --target dynamodb --count 100
  python scripts/populate_test_data.py --target s3 --count 100000
  python scripts/populate_test_data.py --target rds --count 100000 --tacs 8888
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import tempfile
from pathlib import Path
from typing import Any, Iterator

import boto3


DEFAULT_REGION = "us-east-1"
DEFAULT_DDB_TABLE = "legacy-modernization-demo"
DEFAULT_S3_KEY = "legacy-records.json"
DEFAULT_RDS_TABLE = "legacy_records"
DEFAULT_RDS_HANDSET_TABLE = "handset_details"
DEFAULT_RDS_CELL_TABLE = "cells"
BATCH_SIZE = 100


def config(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def records(count: int, tacs: str, seed: int) -> Iterator[dict[str, Any]]:
    generator = random.Random(seed)
    statuses = ("ACTIVE", "READY", "INACTIVE", "PENDING")
    for index in range(1, count + 1):
        yield {
            "id": f"load-{index:08d}",
            "tacs": tacs if tacs else str(generator.choice(("7777", "8888", "9999"))),
            "handset": f"HS-{generator.randint(10000000, 99999999)}",
            "cell": f"CELL-{generator.randint(1000, 9999)}",
            "name": f"Synthetic customer {index}",
            "status": generator.choice(statuses),
            "tags": [tacs, "synthetic", "load-test"],
            "payload": {"origin": "synthetic", "seed": seed, "sequence": index},
        }


def aws_session():
    return boto3.Session(profile_name=config("AWS_PROFILE"), region_name=config("AWS_REGION", DEFAULT_REGION))


def populate_dynamodb(items: Iterator[dict[str, Any]], count: int) -> None:
    table_name = config("DYNAMODB_TABLE", DEFAULT_DDB_TABLE)
    table = aws_session().resource("dynamodb").Table(table_name)
    written = 0
    with table.batch_writer(overwrite_by_pkeys=["id"]) as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
            if written % 10000 == 0:
                print(f"DynamoDB: {written}/{count}")
    print(f"DynamoDB complete: {written} records in {table_name}")


def populate_s3(items: Iterator[dict[str, Any]], count: int) -> None:
    bucket = config("S3_BUCKET")
    if not bucket:
        raise RuntimeError("Set S3_BUCKET")
    key = config("S3_KEY", DEFAULT_S3_KEY)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
        path = Path(handle.name)
        handle.write('{"records":[')
        for index, item in enumerate(items):
            if index:
                handle.write(",")
            json.dump(item, handle, separators=(",", ":"))
        handle.write("]}")
    try:
        aws_session().client("s3").upload_file(
            str(path), bucket, key,
            ExtraArgs={"ContentType": "application/json", "ServerSideEncryption": "AES256"},
        )
    finally:
        path.unlink(missing_ok=True)
    print(f"S3 complete: {count} records in s3://{bucket}/{key}")


def execute_rds(client, resource_arn: str, secret_arn: str, database: str, sql: str, parameter_sets=None) -> None:
    if parameter_sets is None:
        client.execute_statement(resourceArn=resource_arn, secretArn=secret_arn, database=database, sql=sql)
    else:
        client.batch_execute_statement(resourceArn=resource_arn, secretArn=secret_arn, database=database, sql=sql, parameterSets=parameter_sets)


def populate_rds(items: Iterator[dict[str, Any]], count: int) -> None:
    resource_arn = config("RDS_RESOURCE_ARN")
    secret_arn = config("RDS_SECRET_ARN")
    database = config("RDS_DATABASE", "legacydb")
    handset_table = config("RDS_HANDSET_TABLE", DEFAULT_RDS_HANDSET_TABLE)
    cell_table = config("RDS_CELL_TABLE", DEFAULT_RDS_CELL_TABLE)
    if not resource_arn or not secret_arn:
        raise RuntimeError("Set RDS_RESOURCE_ARN and RDS_SECRET_ARN")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or "") for table in (handset_table, cell_table)):
        raise RuntimeError("RDS_HANDSET_TABLE and RDS_CELL_TABLE must be simple SQL identifiers")
    client = aws_session().client("rds-data")
    execute_rds(client, resource_arn, secret_arn, database, f"CREATE TABLE IF NOT EXISTS {cell_table} (cell_id VARCHAR(100) PRIMARY KEY, cell_name VARCHAR(200) NOT NULL, technology VARCHAR(50), status VARCHAR(50) NOT NULL, payload JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    execute_rds(client, resource_arn, secret_arn, database, f"CREATE TABLE IF NOT EXISTS {handset_table} (handset_id VARCHAR(100) PRIMARY KEY, tacs VARCHAR(50) NOT NULL, cell_id VARCHAR(100) REFERENCES {cell_table}(cell_id), handset_model VARCHAR(100), status VARCHAR(50) NOT NULL, payload JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    execute_rds(client, resource_arn, secret_arn, database, f"CREATE INDEX IF NOT EXISTS idx_{handset_table}_tacs ON {handset_table} (tacs)")
    cell_sql = f"INSERT INTO {cell_table} (cell_id,cell_name,technology,status,payload) VALUES (:cell_id,:cell_name,:technology,:status,CAST(:payload AS JSONB)) ON CONFLICT (cell_id) DO UPDATE SET cell_name=EXCLUDED.cell_name,technology=EXCLUDED.technology,status=EXCLUDED.status,payload=EXCLUDED.payload"
    handset_sql = f"INSERT INTO {handset_table} (handset_id,tacs,cell_id,handset_model,status,payload) VALUES (:handset_id,:tacs,:cell_id,:handset_model,:status,CAST(:payload AS JSONB)) ON CONFLICT (handset_id) DO UPDATE SET tacs=EXCLUDED.tacs,cell_id=EXCLUDED.cell_id,handset_model=EXCLUDED.handset_model,status=EXCLUDED.status,payload=EXCLUDED.payload"
    cell_batch = []
    handset_batch = []
    written = 0
    for item in items:
        cell_id = item["cell"]
        cell_batch.append([
            {"name": "cell_id", "value": {"stringValue": cell_id}},
            {"name": "cell_name", "value": {"stringValue": f"Cell site {cell_id}"}},
            {"name": "technology", "value": {"stringValue": "5G"}},
            {"name": "status", "value": {"stringValue": item["status"]}},
            {"name": "payload", "value": {"stringValue": json.dumps(item["payload"], separators=(",", ":"))}},
        ])
        handset_batch.append([
            {"name": "handset_id", "value": {"stringValue": item["id"]}},
            {"name": "tacs", "value": {"stringValue": item["tacs"]}},
            {"name": "cell_id", "value": {"stringValue": cell_id}},
            {"name": "handset_model", "value": {"stringValue": item["handset"]}},
            {"name": "status", "value": {"stringValue": item["status"]}},
            {"name": "payload", "value": {"stringValue": json.dumps(item["payload"], separators=(",", ":"))}},
        ])
        if len(handset_batch) == BATCH_SIZE:
            execute_rds(client, resource_arn, secret_arn, database, cell_sql, cell_batch)
            execute_rds(client, resource_arn, secret_arn, database, handset_sql, handset_batch)
            written += len(handset_batch)
            cell_batch, handset_batch = [], []
            if written % 10000 == 0:
                print(f"RDS: {written}/{count}")
    if handset_batch:
        execute_rds(client, resource_arn, secret_arn, database, cell_sql, cell_batch)
        execute_rds(client, resource_arn, secret_arn, database, handset_sql, handset_batch)
        written += len(handset_batch)
    print(f"RDS complete: {written} handset records in {handset_table} and cell records in {cell_table}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("dynamodb", "s3", "rds"), required=True)
    parser.add_argument("--count", type=int, default=int(config("RECORD_COUNT", "100")))
    parser.add_argument("--tacs", default=config("TEST_TACS", "8888"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.count <= 1_000_000:
        parser.error("--count must be between 1 and 1000000")
    item_stream = records(args.count, args.tacs, args.seed)
    if args.target == "dynamodb":
        populate_dynamodb(item_stream, args.count)
    elif args.target == "s3":
        populate_s3(item_stream, args.count)
    else:
        populate_rds(item_stream, args.count)


if __name__ == "__main__":
    main()
