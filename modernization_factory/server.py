from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .pipeline import propose, validate


DEMO_APPLICATION: dict[str, Any] = {
    "name": "demo-order-service",
    "description": "Legacy order processor with Kafka, RabbitMQ, and an SMB partner drop.",
    "runtime": "java-8",
    "deployment": "vm",
    "data_classification": "internal",
    "tags": {"environment": "sandbox", "owner": "modernization-team", "demo": "true"},
    "interfaces": [
        {"type": "kafka", "direction": "consume", "name": "orders"},
        {"type": "rabbitmq", "direction": "publish", "name": "fulfilment-events"},
        {"type": "smb", "direction": "read", "name": "partner-files", "path": "\\\\fileserver\\orders"},
    ],
}

DEMO_DATA = {
    "s3": [
        {"id": "s3-001", "name": "order-file-001", "tags": ["8888", "orders"], "status": "ready"},
        {"id": "s3-002", "name": "order-file-002", "tags": ["7777", "orders"], "status": "processed"},
    ],
    "rds": [
        {"id": "rds-001", "name": "customer-8888", "tags": ["8888", "customer"], "status": "active"},
        {"id": "rds-002", "name": "customer-9999", "tags": ["9999", "customer"], "status": "inactive"},
    ],
    "dynamodb": [
        {"id": "ddb-001", "name": "DynamoDB record 8888", "tags": ["8888", "demo"], "status": "ACTIVE"},
        {"id": "ddb-002", "name": "DynamoDB record 7777", "tags": ["7777", "demo"], "status": "READY"},
    ],
}


def load_plan(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return validate(propose(DEMO_APPLICATION)).to_dict()


def load_data(source: str | None, tag: str | None) -> list[dict[str, Any]]:
    sources = [source] if source in DEMO_DATA else list(DEMO_DATA) if source in (None, "all") else []
    records = [dict(record, source=item_source.upper()) for item_source in sources for record in DEMO_DATA[item_source]]
    return [record for record in records if not tag or tag in record.get("tags", [])]


def load_dynamodb_data(tag: str | None) -> list[dict[str, Any]]:
    """Read the real sandbox table when MODERNIZATION_DATA_MODE=aws."""
    try:
        import boto3
        from boto3.dynamodb.conditions import Key
    except ImportError as exc:
        raise RuntimeError("Install boto3 before using AWS mode: python -m pip install boto3") from exc

    session = boto3.Session(profile_name=os.getenv("AWS_PROFILE") or None, region_name=os.getenv("AWS_REGION", "us-east-1"))
    table = session.resource("dynamodb").Table(os.getenv("DYNAMODB_TABLE", "legacy-modernization-demo"))
    if tag:
        response = table.query(IndexName=os.getenv("DYNAMODB_INDEX", "tacs-index"), KeyConditionExpression=Key("tacs").eq(tag))
    else:
        response = table.scan()
    return [dict(item, source="DYNAMODB") for item in response.get("Items", [])]


def page(plan: dict[str, Any]) -> str:
    app = plan["application"]
    rows = "".join(
        f"<tr><td>{item['source']}</td><td>{item['target']}</td><td>{item['confidence']}%</td></tr>"
        for item in plan.get("decisions", [])
    )
    tags = " ".join(f"<span>{key}={value}</span>" for key, value in app.get("tags", {}).items())
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Modernization Factory</title>
<style>body{{font:16px Arial;max-width:1000px;margin:40px auto;color:#172033}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd3df;padding:10px;text-align:left}}th{{background:#eef2f7}}span{{background:#e4efff;border-radius:12px;padding:5px 9px;margin-right:5px;display:inline-block}}.status{{font-weight:bold;color:#16794b}}</style>
</head><body><h1>Legacy Modernization Factory</h1>
<p>Application: <strong>{app['name']}</strong> · Status: <strong class='status'>{plan.get('status')}</strong></p>
<p>Tags: {tags}</p><h2>Proposed AWS mappings</h2>
<table><tr><th>Legacy interface</th><th>AWS target</th><th>Confidence</th></tr>{rows}</table>
<h2>Findings</h2><pre>{json.dumps(plan.get('findings', []), indent=2)}</pre>
<p>JSON endpoint: <a href='/api/plan'>/api/plan</a> · Data demo: <a href='/api/data?tags=8888'>/api/data?tags=8888</a> · Health: <a href='/health'>/health</a></p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    plan: dict[str, Any] = {}

    def send_body(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self.send_body(json.dumps({"status": "ok", "service": "modernization-factory"}), "application/json")
        elif parsed.path == "/api/plan":
            self.send_body(json.dumps(self.plan, indent=2), "application/json")
        elif parsed.path == "/api/data":
            tag = (query.get("tags") or query.get("tacs") or [None])[0]
            source = (query.get("source") or [None])[0]
            try:
                records = load_dynamodb_data(tag) if source == "dynamodb" and os.getenv("MODERNIZATION_DATA_MODE") == "aws" else load_data(source, tag)
            except RuntimeError as exc:
                self.send_error(502, str(exc))
                return
            payload = {"source": source or "s3+rds", "tag": tag, "count": len(records), "records": records}
            self.send_body(json.dumps(payload, indent=2), "application/json")
        elif parsed.path == "/":
            self.send_body(page(self.plan), "text/html; charset=utf-8")
        else:
            self.send_error(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Local read-only modernization plan endpoint")
    parser.add_argument("--plan", type=Path, help="Path to generated plan.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    Handler.plan = load_plan(args.plan)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Modernization Factory running at http://{args.host}:{args.port}")
    print("Open / for the display, /api/plan for JSON, or /health for health checks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
