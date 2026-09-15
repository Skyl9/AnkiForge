from dataclasses import dataclass


@dataclass
class LintIssue:
    """Représente une anomalie détectée par le linter dans le code source."""

    line: int  # 1-indexed
    column: int  # 1-indexed
    message: str
    severity: str  # "error" | "warning"
    rule_id: str
