"""Typed errors and exit-code contract for kc."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXIT_OK = 0
EXIT_VALIDATION = 10
EXIT_NOT_FOUND = 11
EXIT_ALREADY_EXISTS = 12
EXIT_CONFLICT = 13
EXIT_PROVENANCE = 20
EXIT_INDEX = 30
EXIT_RETRIEVAL_MODEL = 31
EXIT_WAITING = 40
EXIT_IO = 50
EXIT_LOCK = 60
EXIT_PERSISTENCE = 70
EXIT_UNSUPPORTED = 80
EXIT_INTERNAL = 90


ERROR_EXIT_MAP: dict[str, int] = {
    "KC_CONFIG_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_CONFIG_INVALID": EXIT_VALIDATION,
    "KC_SOURCE_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_SOURCE_ALREADY_REGISTERED": EXIT_ALREADY_EXISTS,
    "KC_SOURCE_STALE": EXIT_PROVENANCE,
    "KC_SOURCE_UNSUPPORTED_MEDIA_TYPE": EXIT_UNSUPPORTED,
    "KC_RANGE_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_ARTIFACT_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_ARTIFACT_SCHEMA_INVALID": EXIT_VALIDATION,
    "KC_ARTIFACT_STATUS_INVALID": EXIT_VALIDATION,
    "KC_CITATION_INVALID_TOKEN": EXIT_PROVENANCE,
    "KC_CITATION_SOURCE_MISSING": EXIT_PROVENANCE,
    "KC_CITATION_RANGE_MISSING": EXIT_PROVENANCE,
    "KC_CITATION_STALE_SOURCE": EXIT_PROVENANCE,
    "KC_VALIDATION_MISSING_CITATION": EXIT_VALIDATION,
    "KC_VALIDATION_TODO_IN_ACTIVE_ARTIFACT": EXIT_VALIDATION,
    "KC_PLAN_PRECONDITION_FAILED": EXIT_CONFLICT,
    "KC_APPLY_REQUIRES_YES": EXIT_VALIDATION,
    "KC_APPLY_NOT_VALIDATED": EXIT_VALIDATION,
    "KC_LOCK_HELD": EXIT_LOCK,
    "KC_INDEX_BUILD_FAILED": EXIT_INDEX,
    "KC_RETRIEVAL_MODEL_UNAVAILABLE": EXIT_RETRIEVAL_MODEL,
    "KC_UNSUPPORTED_FEATURE": EXIT_UNSUPPORTED,
    "KC_PATH_OUTSIDE_REPO": EXIT_VALIDATION,
    "KC_FILE_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_FILE_EXISTS": EXIT_ALREADY_EXISTS,
    "KC_JSON_INVALID": EXIT_VALIDATION,
    "KC_TASK_NOT_FOUND": EXIT_NOT_FOUND,
    "KC_TASK_NOT_WAITING": EXIT_CONFLICT,
    "KC_EVENT_INVALID": EXIT_VALIDATION,
    "KC_INTERNAL_ERROR": EXIT_INTERNAL,
}


ERROR_CATEGORIES: dict[str, str] = {
    "CONFIG": "configuration",
    "SOURCE": "source",
    "RANGE": "source_range",
    "ARTIFACT": "artifact",
    "CITATION": "provenance",
    "VALIDATION": "validation",
    "PLAN": "plan",
    "APPLY": "apply",
    "LOCK": "concurrency",
    "INDEX": "index",
    "RETRIEVAL": "retrieval",
    "PATH": "validation",
    "FILE": "io",
    "JSON": "validation",
    "TASK": "task",
    "EVENT": "task",
    "UNSUPPORTED": "unsupported",
    "INTERNAL": "internal",
}


def exit_code_for(code: str) -> int:
    return ERROR_EXIT_MAP.get(code, EXIT_INTERNAL)


def category_for(code: str) -> str:
    parts = code.split("_")
    if len(parts) >= 2:
        return ERROR_CATEGORIES.get(parts[1], "internal")
    return "internal"


@dataclass
class KcError(Exception):
    """Domain error surfaced through the kc.result.v1 envelope."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    category: str | None = None
    exit_code: int | None = None
    retryable: bool = False
    suggested_action: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if self.category is None:
            self.category = category_for(self.code)
        if self.exit_code is None:
            self.exit_code = exit_code_for(self.code)
        if self.suggested_action is None:
            if self.retryable:
                self.suggested_action = "retry"
            elif self.exit_code in {EXIT_VALIDATION, EXIT_NOT_FOUND, EXIT_ALREADY_EXISTS}:
                self.suggested_action = "fix_input"
            elif self.exit_code == EXIT_LOCK:
                self.suggested_action = "inspect lock with kc doctor locks or retry later"
            else:
                self.suggested_action = "escalate"

    def to_message(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "exit_code": self.exit_code,
            "retryable": self.retryable,
            "suggested_action": self.suggested_action,
            "details": self.details,
        }


def validation_error(
    message: str, *, code: str = "KC_ARTIFACT_SCHEMA_INVALID", **details: Any
) -> KcError:
    return KcError(code=code, message=message, details=details)
