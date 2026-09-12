"""Typed results and task records. No secrets stored."""

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .constants import ALL_STAGES, REVIEW_VERDICTS, SHA256_RE, TASK_ID_RE

KIND_OK = "ok"
KIND_EMPTY = "empty"
KIND_NONZERO = "nonzero"
KIND_MAX_TURNS = "max_turns"
KIND_AUTH = "auth"
KIND_RATE_LIMIT = "rate_limit"
KIND_DISABLED = "disabled"
KIND_TIMEOUT = "timeout"
KIND_OVERFLOW = "overflow"
KIND_CANCELLED = "cancelled"
KIND_INVALID = "invalid"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ClientResult:
    kind: str
    text: str = ""
    exit_code: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self):
        return (
            self.kind == KIND_OK
            and self.exit_code == 0
            and isinstance(self.text, str)
            and bool(self.text.strip())
        )


@dataclass
class ReviewParse:
    verdict: str
    explanation: str

    def valid(self):
        return self.verdict in REVIEW_VERDICTS and bool(self.explanation.strip())


def parse_review_payload(text):
    """Accept a small structured review. Exit 0 alone is never a pass."""
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    import json

    try:
        data = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if set(data.keys()) != {"verdict", "explanation"}:
        return None
    verdict = data.get("verdict")
    explanation = data.get("explanation")
    if not isinstance(verdict, str) or not isinstance(explanation, str):
        return None
    if verdict.strip() != verdict or explanation.strip() != explanation:
        return None
    parsed = ReviewParse(verdict=verdict, explanation=explanation)
    if not parsed.valid():
        return None
    return parsed


@dataclass
class TaskRecord:
    task_id: str
    requirement: str
    project: str
    owner_open_id: str
    owner_chat_id: str
    stage: str
    created_at: str
    updated_at: str
    prd_hash: Optional[str] = None
    approved_hash: Optional[str] = None
    approval_event: Optional[str] = None
    last_error: Optional[str] = None
    last_message_id: Optional[str] = None
    seen_message_ids: list = field(default_factory=list)
    build_artifact: Optional[str] = None
    review_artifact: Optional[str] = None
    prd_artifact: Optional[str] = None
    artifact_versions: Dict[str, int] = field(default_factory=dict)
    handoff_round: int = 0
    last_delivery_status: Optional[str] = None
    last_handoff_status: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("invalid task json")
        required = (
            "task_id",
            "requirement",
            "project",
            "owner_open_id",
            "owner_chat_id",
            "stage",
            "created_at",
            "updated_at",
        )
        for key in required:
            if key not in data:
                raise ValueError("missing field %s" % key)
            if not isinstance(data[key], str) or not data[key]:
                raise ValueError("invalid field %s" % key)
        if not TASK_ID_RE.match(data["task_id"]):
            raise ValueError("invalid task id")
        if data["stage"] not in ALL_STAGES:
            raise ValueError("invalid stage")
        optional_str = (
            "prd_hash",
            "approved_hash",
            "approval_event",
            "last_error",
            "last_message_id",
            "build_artifact",
            "review_artifact",
            "prd_artifact",
            "last_delivery_status",
            "last_handoff_status",
        )
        kwargs = {k: data[k] for k in required}
        for key in optional_str:
            value = data.get(key)
            if value is None:
                kwargs[key] = None
            elif isinstance(value, str):
                kwargs[key] = value
            else:
                raise ValueError("invalid field %s" % key)
        for digest_key in ("prd_hash", "approved_hash"):
            digest = kwargs.get(digest_key)
            if digest is not None and not SHA256_RE.match(digest):
                raise ValueError("invalid digest %s" % digest_key)
        seen = data.get("seen_message_ids", [])
        if not isinstance(seen, list) or any(not isinstance(x, str) for x in seen):
            raise ValueError("invalid seen_message_ids")
        kwargs["seen_message_ids"] = list(seen)
        versions = data.get("artifact_versions", {})
        if not isinstance(versions, dict):
            raise ValueError("invalid artifact_versions")
        clean_versions = {}
        for key, value in versions.items():
            if not isinstance(key, str) or not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("invalid artifact_versions")
            clean_versions[key] = value
        kwargs["artifact_versions"] = clean_versions
        round_value = data.get("handoff_round", 0)
        if round_value is None:
            round_value = 0
        if not isinstance(round_value, int) or isinstance(round_value, bool) or round_value < 0:
            raise ValueError("invalid handoff_round")
        kwargs["handoff_round"] = round_value
        return cls(**kwargs)
