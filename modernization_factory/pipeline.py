from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import Decision, Finding, Plan


SECRET_KEY = re.compile(r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key)", re.I)
SECRET_VALUE = re.compile(r"(?i)(bearer\s+|aws_secret_access_key\s*=\s*|-----BEGIN [A-Z ]+PRIVATE KEY-----)")


def sanitize(value: Any) -> Any:
    """Recursively remove common credential material before analysis."""
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEY.search(str(key)) else sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str) and SECRET_VALUE.search(value):
        return "[REDACTED]"
    return value


def read_intake(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or not raw.get("name"):
        raise ValueError("Intake must be an object containing a non-empty 'name'")
    return sanitize(raw)


def propose(application: dict[str, Any]) -> Plan:
    decisions: list[Decision] = []
    findings: list[Finding] = []
    for interface in application.get("interfaces", []):
        kind = str(interface.get("type", "")).lower()
        mapping = {
            "kafka": ("Amazon MSK", "Preserves Kafka client and topic semantics.", 90),
            "rabbitmq": ("Amazon MQ for RabbitMQ", "Managed RabbitMQ reduces broker operations work.", 90),
            "smb": ("AWS DataSync to Amazon S3", "Moves file exchange into durable AWS-managed storage.", 80),
            "rest": ("Amazon API Gateway plus ECS service", "Provides a managed edge for an HTTP workload.", 70),
        }
        target, rationale, confidence = mapping.get(
            kind,
            ("Manual assessment required", "No built-in mapping exists for this interface.", 20),
        )
        decisions.append(Decision(kind or "unknown", target, rationale, confidence))
        if kind == "smb" and interface.get("path"):
            findings.append(Finding("info", "SMB_SOURCE", f"SMB source recorded: {interface['path']}"))
        if kind not in mapping:
            findings.append(Finding("error", "UNMAPPED_INTERFACE", f"No safe mapping for interface type '{kind or 'missing'}'"))

    runtime = str(application.get("runtime", "")).lower()
    compute = "ECS Fargate"
    if "windows" in runtime:
        compute = "EC2 Windows"
        findings.append(Finding("warning", "WINDOWS_RUNTIME", "Windows runtime requires image and licensing validation."))
    decisions.append(Decision("application-runtime", compute, "Default sandbox compute target based on the supplied runtime.", 75))
    if application.get("data_classification") in {"confidential", "restricted", "pii"}:
        findings.append(Finding("warning", "SENSITIVE_DATA", "Use masked test data and an approved KMS/key policy before deployment."))
    return Plan(application=application, decisions=decisions, findings=findings)


def validate(plan: Plan) -> Plan:
    if not plan.application.get("interfaces"):
        plan.findings.append(Finding("warning", "NO_INTERFACES", "No interfaces were supplied; integration coverage will be limited."))
    if not plan.application.get("data_classification"):
        plan.findings.append(Finding("warning", "MISSING_CLASSIFICATION", "Data classification is missing."))
    if any(f.severity == "error" for f in plan.findings):
        plan.status = "blocked"
    else:
        plan.status = "validated"
    return plan


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_plan(intake_path: Path, output_dir: Path) -> Plan:
    application = read_intake(intake_path)
    write_json(output_dir / "sanitized-intake.json", application)
    plan = validate(propose(application))
    write_json(output_dir / "plan.json", plan.to_dict())
    return plan


def deploy_locally(plan: Plan, output_dir: Path, approved: bool) -> dict[str, Any]:
    if not approved:
        raise PermissionError("Human approval is required; pass --approve to deploy")
    if plan.status == "blocked":
        raise RuntimeError("Plan is blocked by validation errors")
    manifest = {
        "mode": "local-sandbox-simulation",
        "application": plan.application["name"],
        "resources": [{"kind": decision.target, "source": decision.source} for decision in plan.decisions],
        "rollback": "Delete this manifest; no AWS resources were created.",
    }
    write_json(output_dir / "sandbox-manifest.json", manifest)
    report = {"status": "passed", "checks": ["manifest-created", "approval-present", "validation-passed"]}
    write_json(output_dir / "test-report.json", report)
    return report
