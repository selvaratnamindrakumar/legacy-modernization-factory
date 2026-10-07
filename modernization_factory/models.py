from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    severity: str
    code: str
    message: str


@dataclass
class Decision:
    source: str
    target: str
    rationale: str
    confidence: int


@dataclass
class Plan:
    application: dict[str, Any]
    decisions: list[Decision] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    status: str = "proposed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Plan":
        return cls(
            application=value["application"],
            decisions=[Decision(**item) for item in value.get("decisions", [])],
            findings=[Finding(**item) for item in value.get("findings", [])],
            status=value.get("status", "proposed"),
        )
