"""Failure categories: Apollo Research's 13 public Watcher Live failure modes, plus 'other'."""

CATEGORIES = (
    "data_exfiltration",
    "resource_exposure",
    "prompt_injection",
    "infrastructure_disruption",
    "shared_resource_destruction",
    "undesirable_deletion",
    "oversight_subversion",
    "unsafe_agent",
    "untrusted_code_execution",
    "real_world_transaction",
    "vulnerability_introduction",
    "unapproved_dependency",
    "privilege_escalation",
    "other",
)


def normalize_category(value) -> str:
    return value if value in CATEGORIES else "other"
