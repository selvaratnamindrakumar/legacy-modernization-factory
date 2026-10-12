from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .pipeline import deploy_locally, run_plan
from .models import Plan


DEMO = {
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Local legacy modernization factory")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--output-dir", type=Path, default=Path("sandbox-output"))
    plan = sub.add_parser("plan")
    plan.add_argument("intake", type=Path)
    plan.add_argument("--output-dir", type=Path, default=Path("sandbox-output"))
    deploy = sub.add_parser("deploy")
    deploy.add_argument("plan", type=Path)
    deploy.add_argument("--approve", action="store_true")
    deploy.add_argument("--output-dir", type=Path, default=Path("sandbox-output"))
    args = parser.parse_args()

    if args.command == "demo":
        with tempfile.TemporaryDirectory() as directory:
            intake = Path(directory) / "demo.json"
            intake.write_text(json.dumps(DEMO), encoding="utf-8")
            result = run_plan(intake, args.output_dir)
    elif args.command == "plan":
        result = run_plan(args.intake, args.output_dir)
    else:
        result = Plan.from_dict(json.loads(args.plan.read_text(encoding="utf-8")))
        report = deploy_locally(result, args.output_dir, args.approve)
        print(json.dumps(report, indent=2))
        return 0
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
