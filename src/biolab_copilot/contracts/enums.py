"""Enumerations shared by public contracts."""

from enum import StrEnum


class RunStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    READY = "READY"
    ANALYZING = "ANALYZING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


__all__ = ["IssueSeverity", "RunStatus"]

