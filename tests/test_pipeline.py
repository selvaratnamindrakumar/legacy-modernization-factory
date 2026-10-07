import json
import tempfile
import unittest
from pathlib import Path

from modernization_factory.pipeline import deploy_locally, propose, read_intake, run_plan, sanitize
from modernization_factory.models import Plan


class PipelineTests(unittest.TestCase):
    def test_sanitize_redacts_nested_secrets(self):
        value = sanitize({"config": {"password": "do-not-export", "name": "ok"}})
        self.assertEqual(value["config"]["password"], "[REDACTED]")
        self.assertEqual(value["config"]["name"], "ok")

    def test_known_interfaces_are_mapped(self):
        plan = propose({"name": "x", "interfaces": [{"type": "kafka"}, {"type": "rabbitmq"}, {"type": "smb"}]})
        targets = {decision.target for decision in plan.decisions}
        self.assertIn("Amazon MSK", targets)
        self.assertIn("Amazon MQ for RabbitMQ", targets)
        self.assertIn("AWS DataSync to Amazon S3", targets)

    def test_unknown_interface_blocks_plan(self):
        plan = run_plan_from_object({"name": "x", "interfaces": [{"type": "proprietary-bus"}]})
        self.assertEqual(plan.status, "blocked")

    def test_deploy_requires_approval_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            plan = Plan(application={"name": "x"}, status="validated")
            with self.assertRaises(PermissionError):
                deploy_locally(plan, output, approved=False)
            report = deploy_locally(plan, output, approved=True)
            self.assertEqual(report["status"], "passed")
            self.assertTrue((output / "sandbox-manifest.json").exists())


def run_plan_from_object(value):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        intake = root / "intake.json"
        output = root / "output"
        intake.write_text(json.dumps(value), encoding="utf-8")
        return run_plan(intake, output)


if __name__ == "__main__":
    unittest.main()
