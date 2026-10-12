from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

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


def load_plan(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return validate(propose(DEMO_APPLICATION)).to_dict()


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
<p>JSON endpoint: <a href='/api/plan'>/api/plan</a> · Health: <a href='/health'>/health</a></p>
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
        if self.path == "/health":
            self.send_body(json.dumps({"status": "ok", "service": "modernization-factory"}), "application/json")
        elif self.path == "/api/plan":
            self.send_body(json.dumps(self.plan, indent=2), "application/json")
        elif self.path == "/":
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
