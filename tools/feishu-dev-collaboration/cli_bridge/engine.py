"""Task state machine. Approval is owner-only; models cannot approve."""

from .clients import clients_from_policy
from .constants import (
    ARTIFACT_PAGE_CHARS,
    ARTIFACT_SELECTORS,
    CLI_ROLE_BOTH,
    CLI_ROLE_CODEX,
    CLI_ROLE_GROK,
    MAX_HANDOFF_ROUNDS,
    MAX_PRD_CHARS,
    MAX_REPORT_CHARS,
    MAX_REQUIREMENT_CHARS,
    SHA256_RE,
    STAGE_APPROVED,
    STAGE_BUILDING,
    STAGE_BUILT,
    STAGE_CANCELLED,
    STAGE_DRAFT,
    STAGE_DRAFTING,
    STAGE_FAILED,
    STAGE_NEEDS_CHANGES,
    STAGE_NEEDS_USER,
    STAGE_RATE_LIMITED,
    STAGE_READY_FOR_PR,
    STAGE_REVIEWING,
    TASK_ID_RE,
)
from .delivery import DELIVERY_STATUSES, delivery_token
from .summary import human_summary_ok
from .handoff import peer_handoff_command
from .route import normalize_id_list
from .models import (
    KIND_AUTH,
    KIND_DISABLED,
    KIND_OK,
    KIND_RATE_LIMIT,
    ClientResult,
    TaskRecord,
    parse_review_payload,
    sha256_text,
)
from .sanitize import preview, reject_invalid_text, safe_text, sanitize_persisted
from .store import TaskStore, new_task_id, utcnow


class TaskEngine:
    def __init__(
        self,
        store,
        clients=None,
        execution_policy=None,
        owner_open_id="",
        owner_chat_id="",
        cli_role="",
        trusted_peer_open_ids=None,
        owner_alias_open_ids=None,
    ):
        self.store = store
        self.clients = clients if clients is not None else clients_from_policy(execution_policy)
        self.owner_open_id = owner_open_id
        self.owner_chat_id = owner_chat_id
        self.cli_role = (cli_role or CLI_ROLE_BOTH).strip().lower() or CLI_ROLE_BOTH
        self.trusted_peer_open_ids = set(normalize_id_list(trusted_peer_open_ids))
        self.owner_alias_open_ids = set(normalize_id_list(owner_alias_open_ids))
        self.split_handoff = self.cli_role in (CLI_ROLE_CODEX, CLI_ROLE_GROK)
        self._jobs = {}
        self._seen = set()

    def _same_person_ids(self):
        ids = set()
        if self.owner_open_id:
            ids.add(self.owner_open_id)
        ids.update(self.owner_alias_open_ids)
        return ids

    def _can_act(self, rec, actor_open_id, human_only=False):
        if not actor_open_id:
            return False
        same = self._same_person_ids()
        if not same or rec.owner_open_id not in same:
            return False
        if actor_open_id == self.owner_open_id:
            return True
        if human_only:
            return False
        return actor_open_id in self.trusted_peer_open_ids

    def _require_role(self, action):
        if self.cli_role in ("", CLI_ROLE_BOTH):
            return
        need = {
            "draft": CLI_ROLE_CODEX,
            "approve": CLI_ROLE_CODEX,
            "review": CLI_ROLE_CODEX,
            "build": CLI_ROLE_GROK,
        }.get(action)
        if need and self.cli_role != need:
            raise PermissionError("role mismatch")

    def has_live_job(self):
        for job in list(self._jobs.values()):
            if job is not None and not job.done():
                return True
        return False

    def _reject_if_busy(self):
        if self.has_live_job():
            raise RuntimeError("concurrent task")
        if self.store.active_for_project():
            raise RuntimeError("concurrent task")

    def _remember_message(self, rec, message_id):
        if not message_id:
            return False
        if message_id in rec.seen_message_ids:
            return True
        if self._message_known(message_id):
            return True
        rec.seen_message_ids.append(message_id)
        rec.last_message_id = message_id
        self._seen.add(message_id)
        return False

    def _message_known(self, message_id):
        if not message_id:
            return False
        if message_id in self._seen:
            return True
        for rec in self.store.list_records():
            if message_id in rec.seen_message_ids:
                self._seen.add(message_id)
                return True
        return False

    def record_by_message(self, message_id):
        for rec in self.store.list_records():
            if message_id in rec.seen_message_ids:
                return rec
        return None

    def note_send_failure(self, task_id, detail):
        return self.note_delivery(task_id, channel="user", status=detail)

    def note_delivery(self, task_id, channel, status):
        rec = self.store.load(task_id)
        token = delivery_token(status)
        if token not in DELIVERY_STATUSES:
            token = "send_unsuccessful"
        if channel == "handoff":
            rec.last_handoff_status = token
        else:
            rec.last_delivery_status = token
        if token not in ("ok", "skipped"):
            rec.last_error = safe_text("delivery failed: %s" % token)
        elif channel == "user" and rec.last_error and rec.last_error.startswith("delivery failed:"):
            rec.last_error = None
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec

    def request_resend(self, task_id, actor_open_id, message_id, target="user"):
        if target not in ("user", "handoff"):
            raise ValueError("invalid resend target")
        rec = self.store.load(task_id)
        if not self._can_act(rec, actor_open_id, human_only=True):
            raise PermissionError("owner mismatch")
        if rec.stage == STAGE_CANCELLED:
            raise RuntimeError("cancelled")
        if target == "user" and rec.stage == STAGE_DRAFTING:
            raise RuntimeError("not ready")
        if target == "handoff" and peer_handoff_command(rec) is None:
            raise RuntimeError("no handoff")
        if self._message_known(message_id):
            return rec, True
        self._remember_message(rec, message_id)
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec, False

    def _fail(self, rec, stage, err):
        rec.stage = stage
        rec.last_error = safe_text(err)
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec

    def start_draft(self, requirement, message_id, owner_open_id, owner_chat_id):
        self._require_role("draft")
        requirement = reject_invalid_text(requirement, MAX_REQUIREMENT_CHARS, "requirement")
        if message_id and self._message_known(message_id):
            existing = self.record_by_message(message_id)
            if existing is not None:
                return existing, True
        self._reject_if_busy()
        rec = TaskRecord(
            task_id=new_task_id(),
            requirement=requirement,
            project=self.store.project_root,
            owner_open_id=owner_open_id,
            owner_chat_id=owner_chat_id,
            stage=STAGE_DRAFTING,
            created_at=utcnow(),
            updated_at=utcnow(),
            last_message_id=message_id,
            seen_message_ids=[message_id] if message_id else [],
        )
        if message_id:
            self._seen.add(message_id)
        self.store.save(rec)
        return rec, False

    async def run_draft(self, task_id):
        rec = self.store.load(task_id)
        if rec.stage != STAGE_DRAFTING:
            return rec
        result = await self.clients.draft(rec.requirement, rec.project)
        rec = self.store.load(task_id)
        if rec.stage == STAGE_CANCELLED:
            rec.last_error = "Cancelled; no filesystem rollback."
            self.store.save(rec)
            return rec
        if rec.stage != STAGE_DRAFTING:
            return rec
        return self._apply_draft_result(rec, result)

    def _apply_draft_result(self, rec, result):
        if rec.stage == STAGE_CANCELLED:
            rec.last_error = "Cancelled."
            self.store.save(rec)
            return rec
        if result.kind == KIND_DISABLED:
            return self._fail(rec, STAGE_NEEDS_USER, self._disabled_message(result))
        if result.kind == KIND_RATE_LIMIT:
            return self._fail(rec, STAGE_RATE_LIMITED, "Rate limited.")
        if result.kind == KIND_AUTH:
            return self._fail(rec, STAGE_FAILED, "Auth failure.")
        if not result.ok:
            return self._fail(rec, STAGE_FAILED, "Draft failed.")
        text = reject_invalid_text(sanitize_persisted(result.text), MAX_PRD_CHARS, "prd")
        digest = sha256_text(text)
        rec.prd_hash = digest
        rec.prd_artifact = self.store.write_artifact(rec.task_id, "prd", text, version=1)
        rec.stage = STAGE_DRAFT
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec

    def approve(self, task_id, digest, owner_open_id, message_id):
        self._require_role("approve")
        if not TASK_ID_RE.match(task_id or ""):
            raise ValueError("invalid task id")
        if not SHA256_RE.match(digest or ""):
            raise ValueError("invalid digest")
        rec = self.store.load(task_id)
        if not self._can_act(rec, owner_open_id, human_only=True):
            raise PermissionError("owner mismatch")
        if rec.stage == STAGE_CANCELLED:
            raise RuntimeError("cancelled")
        if rec.stage == STAGE_APPROVED and rec.approved_hash == digest:
            return rec
        if rec.stage not in (STAGE_DRAFT, STAGE_NEEDS_USER):
            raise RuntimeError("not approvable")
        if not rec.prd_artifact or not rec.prd_hash:
            raise RuntimeError("no prd")
        prd = self.store.read_artifact(rec.task_id, rec.prd_artifact)
        current = sha256_text(prd)
        if rec.prd_hash != current:
            return self._fail(rec, STAGE_FAILED, "PRD tampered.")
        if digest != current:
            raise ValueError("digest mismatch")
        rec.approved_hash = current
        rec.approval_event = "owner:%s:%s" % (owner_open_id, message_id or "")
        rec.stage = STAGE_APPROVED
        rec.updated_at = utcnow()
        rec.last_error = None
        self.store.save(rec)
        return rec

    def _disabled_message(self, result):
        reason = None
        extra = getattr(result, "extra", None)
        if isinstance(extra, dict):
            reason = extra.get("reason")
        if isinstance(reason, str) and reason and all(ch.islower() or ch == "_" for ch in reason):
            return "Live execution disabled (%s)." % reason
        return "Live execution disabled."

    def _prd_still_valid(self, rec):
        if not rec.prd_artifact or not rec.approved_hash:
            return False
        prd = self.store.read_artifact(rec.task_id, rec.prd_artifact)
        return sha256_text(prd) == rec.approved_hash == rec.prd_hash

    def request_build(self, task_id, owner_open_id, message_id):
        self._require_role("build")
        rec = self.store.load(task_id)
        if not self._can_act(rec, owner_open_id, human_only=False):
            raise PermissionError("owner mismatch")
        if rec.stage == STAGE_CANCELLED:
            raise RuntimeError("cancelled")
        if self._message_known(message_id):
            rec.last_error = "duplicate message"
            self.store.save(rec)
            return rec, True
        if rec.stage not in (STAGE_APPROVED, STAGE_NEEDS_CHANGES, STAGE_NEEDS_USER):
            raise RuntimeError("not buildable")
        if rec.stage == STAGE_NEEDS_USER and not rec.approved_hash:
            raise RuntimeError("not buildable")
        if not self._prd_still_valid(rec):
            self._fail(rec, STAGE_FAILED, "PRD hash invalid.")
            raise RuntimeError("prd invalid")
        if rec.handoff_round >= MAX_HANDOFF_ROUNDS:
            self._fail(rec, STAGE_FAILED, "handoff round limit")
            raise RuntimeError("handoff round limit")
        self._reject_if_busy()
        self._remember_message(rec, message_id)
        rec.handoff_round += 1
        rec.stage = STAGE_BUILDING
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec, False

    async def run_build(self, task_id):
        rec = self.store.load(task_id)
        if rec.stage != STAGE_BUILDING:
            return rec
        prd = self.store.read_artifact(rec.task_id, rec.prd_artifact)
        prior = ""
        if rec.review_artifact:
            prior = self.store.read_artifact(rec.task_id, rec.review_artifact)
        result = await self.clients.build(prd, prior, rec.project)
        rec = self.store.load(task_id)
        if rec.stage == STAGE_CANCELLED:
            rec.last_error = "Cancelled; no filesystem rollback."
            self.store.save(rec)
            return rec
        if rec.stage != STAGE_BUILDING:
            return rec
        if not self._prd_still_valid(rec):
            return self._fail(rec, STAGE_FAILED, "PRD hash invalid.")
        if result.kind == KIND_DISABLED:
            return self._fail(rec, STAGE_NEEDS_USER, self._disabled_message(result))
        if result.kind == KIND_RATE_LIMIT:
            return self._fail(rec, STAGE_RATE_LIMITED, "Rate limited.")
        if result.kind == KIND_AUTH:
            return self._fail(rec, STAGE_FAILED, "Auth failure.")
        if not result.ok:
            return self._fail(rec, STAGE_FAILED, "Build failed.")
        text = reject_invalid_text(sanitize_persisted(result.text), MAX_REPORT_CHARS, "build")
        version = rec.artifact_versions.get("build", 0) + 1
        rec.artifact_versions["build"] = version
        rec.build_artifact = self.store.write_artifact(rec.task_id, "build", text, version=version)
        rec.last_error = None
        rec.updated_at = utcnow()
        if self.split_handoff:
            rec.stage = STAGE_BUILT
            self.store.save(rec)
            return rec
        rec.stage = STAGE_REVIEWING
        self.store.save(rec)
        return await self.run_review(task_id)

    def request_review(self, task_id, owner_open_id, message_id):
        self._require_role("review")
        rec = self.store.load(task_id)
        if not self._can_act(rec, owner_open_id, human_only=False):
            raise PermissionError("owner mismatch")
        if self._message_known(message_id):
            return rec, True
        if rec.stage == STAGE_CANCELLED:
            raise RuntimeError("cancelled")
        if rec.stage == STAGE_REVIEWING:
            raise RuntimeError("concurrent task")
        allowed = (
            STAGE_BUILT,
            STAGE_NEEDS_USER,
            STAGE_NEEDS_CHANGES,
            STAGE_READY_FOR_PR,
            STAGE_FAILED,
            STAGE_RATE_LIMITED,
        )
        if rec.stage not in allowed or not rec.build_artifact:
            raise RuntimeError("no build")
        if not rec.approved_hash or not rec.prd_artifact:
            raise RuntimeError("no build")
        if not self._prd_still_valid(rec):
            self._fail(rec, STAGE_FAILED, "PRD hash invalid.")
            raise RuntimeError("prd invalid")
        if rec.handoff_round >= MAX_HANDOFF_ROUNDS:
            self._fail(rec, STAGE_FAILED, "handoff round limit")
            raise RuntimeError("handoff round limit")
        self._reject_if_busy()
        self._remember_message(rec, message_id)
        rec.handoff_round += 1
        rec.stage = STAGE_REVIEWING
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec, False

    async def run_review(self, task_id):
        rec = self.store.load(task_id)
        if rec.stage != STAGE_REVIEWING:
            return rec
        prd = self.store.read_artifact(rec.task_id, rec.prd_artifact)
        report = self.store.read_artifact(rec.task_id, rec.build_artifact)
        result = await self.clients.review(prd, report, rec.project)
        rec = self.store.load(task_id)
        if rec.stage == STAGE_CANCELLED:
            rec.last_error = "Cancelled; no filesystem rollback."
            self.store.save(rec)
            return rec
        if rec.stage != STAGE_REVIEWING:
            return rec
        if not self._prd_still_valid(rec):
            return self._fail(rec, STAGE_FAILED, "PRD hash invalid.")
        if result.kind == KIND_DISABLED:
            return self._fail(rec, STAGE_NEEDS_USER, self._disabled_message(result))
        if result.kind == KIND_RATE_LIMIT:
            return self._fail(rec, STAGE_RATE_LIMITED, "Rate limited.")
        if result.kind == KIND_AUTH:
            return self._fail(rec, STAGE_FAILED, "Auth failure.")
        if not result.ok:
            return self._fail(rec, STAGE_FAILED, "Review failed.")
        parsed = parse_review_payload(result.text)
        if parsed is None:
            return self._fail(rec, STAGE_FAILED, "Invalid review payload.")
        version = rec.artifact_versions.get("review", 0) + 1
        rec.artifact_versions["review"] = version
        review_text = reject_invalid_text(
            sanitize_persisted(result.text), MAX_REPORT_CHARS, "review"
        )
        rec.review_artifact = self.store.write_artifact(
            rec.task_id, "review", review_text, version=version
        )
        if parsed.verdict == "pass":
            rec.stage = STAGE_READY_FOR_PR
        elif parsed.verdict == "needs_changes":
            rec.stage = STAGE_NEEDS_CHANGES
        else:
            rec.stage = STAGE_FAILED
        rec.last_error = None
        rec.updated_at = utcnow()
        self.store.save(rec)
        return rec

    def cancel(self, task_id, owner_open_id):
        rec = self.store.load(task_id)
        if not self._can_act(rec, owner_open_id, human_only=True):
            raise PermissionError("owner mismatch")
        if rec.stage == STAGE_CANCELLED:
            return rec
        rec.stage = STAGE_CANCELLED
        rec.last_error = "Cancelled; no filesystem rollback."
        rec.updated_at = utcnow()
        self.store.save(rec)
        job = self._jobs.get(task_id)
        if job is not None and not job.done():
            job.cancel()
        return rec

    def fail_job(self, task_id, err):
        rec = self.store.load(task_id)
        if rec.stage == STAGE_CANCELLED:
            return rec
        return self._fail(rec, STAGE_FAILED, err)

    def status(self, task_id=None):
        if task_id:
            rec = self.store.load(task_id)
            return [rec]
        return self.store.list_records()

    def summarize(self, rec):
        return safe_text(
            "task=%s stage=%s prd=%s err=%s preview=%s"
            % (
                rec.task_id,
                rec.stage,
                rec.prd_hash or "-",
                rec.last_error or "-",
                preview(rec.requirement),
            )
        )

    def completion_message(self, rec, handoff_status=None):
        base = self.summarize(rec)
        if rec.stage == STAGE_DRAFT and rec.prd_hash:
            text = (
                "%s\n用 /dev-approve 提交本任务的 prd hash。"
                "全文用 /dev-artifact 分页阅读。Do not auto-approve."
                % base
            )
        elif rec.stage == STAGE_APPROVED:
            text = "%s\n已向 builder 发出 /dev-build" % base
        elif rec.stage == STAGE_BUILT:
            text = "%s\n已向 architect 发出 /dev-review" % base
        elif rec.stage == STAGE_NEEDS_CHANGES:
            text = "%s\n已向 builder 发出 /dev-build" % base
        else:
            text = base
        if handoff_status and handoff_status not in ("ok", "skipped"):
            text = "%s\n交接送达失败。" % text
        if not human_summary_ok(text):
            text = base
            if handoff_status and handoff_status not in ("ok", "skipped"):
                text = "%s\n交接送达失败。" % text
        return text

    def paged_artifact(self, task_id, selector, page, owner_open_id):
        if not TASK_ID_RE.match(task_id or ""):
            raise ValueError("invalid task id")
        if selector not in ARTIFACT_SELECTORS:
            raise ValueError("invalid selector")
        rec = self.store.load(task_id)
        if not self._can_act(rec, owner_open_id, human_only=False):
            raise PermissionError("owner mismatch")
        mapping = {
            "prd": rec.prd_artifact,
            "build": rec.build_artifact,
            "review": rec.review_artifact,
        }
        filename = mapping[selector]
        if not filename:
            raise RuntimeError("no artifact")
        text = self.store.read_artifact(rec.task_id, filename)
        digest = sha256_text(text)
        total = max(1, (len(text) + ARTIFACT_PAGE_CHARS - 1) // ARTIFACT_PAGE_CHARS)
        if not isinstance(page, int) or page < 1 or page > total:
            raise ValueError("invalid page")
        start = (page - 1) * ARTIFACT_PAGE_CHARS
        chunk = text[start : start + ARTIFACT_PAGE_CHARS]
        return "artifact=%s sha256=%s page=%s/%s\n%s" % (
            selector,
            digest,
            page,
            total,
            chunk,
        )
