"""Atomic task store outside the model-writable project."""

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .constants import (
    DIR_MODE,
    FILE_MODE,
    IN_PROGRESS_STAGES,
    MAX_ARTIFACT_BYTES,
    MAX_STATE_BYTES,
    STAGE_NEEDS_USER,
    TASK_ID_RE,
)
from .models import TaskRecord


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_task_id():
    return uuid.uuid4().hex


def _reject_symlink_ancestors(path):
    current = os.path.abspath(path)
    seen = set()
    while current not in seen:
        seen.add(current)
        if os.path.lexists(current) and os.path.islink(current):
            raise ValueError("symlink path rejected")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def _reject_symlinks_under(path, root):
    """Reject symlinks at path or between path and configured root, not OS prefixes."""
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    current = path
    while True:
        if os.path.lexists(current) and os.path.islink(current):
            raise ValueError("symlink path rejected")
        if current == root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        if not (root == parent or root.startswith(parent + os.sep) or current.startswith(root + os.sep) or current == root):
            break
        current = parent


def _is_contained(inner, outer):
    inner_n = os.path.realpath(inner).rstrip(os.sep) + os.sep
    outer_n = os.path.realpath(outer).rstrip(os.sep) + os.sep
    return inner_n == outer_n or inner_n.startswith(outer_n)


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _read_bounded(path, max_bytes):
    with open(path, "rb") as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file exceeds bound")
    return data


class TaskStore:
    def __init__(self, data_root, project_root):
        if not os.path.isabs(data_root) or not os.path.isabs(project_root):
            raise ValueError("roots must be absolute")
        _reject_symlink_ancestors(data_root)
        _reject_symlink_ancestors(project_root)
        if os.path.exists(data_root):
            _reject_symlink_ancestors(data_root)
        if os.path.exists(project_root):
            _reject_symlink_ancestors(project_root)
        data_real = os.path.realpath(data_root)
        project_real = os.path.realpath(project_root)
        if _is_contained(data_real, project_real):
            raise ValueError("data root cannot live inside project")
        self.data_root = data_real
        self.project_root = project_real
        os.makedirs(self.data_root, mode=DIR_MODE, exist_ok=True)
        os.chmod(self.data_root, DIR_MODE)
        self._tasks_dir = os.path.join(self.data_root, "tasks")
        if os.path.lexists(self._tasks_dir):
            _reject_symlink_ancestors(self._tasks_dir)
        os.makedirs(self._tasks_dir, mode=DIR_MODE, exist_ok=True)
        os.chmod(self._tasks_dir, DIR_MODE)
        _reject_symlink_ancestors(self._tasks_dir)
        self._lock_path = os.path.join(self.data_root, "store.lock")
        self._recover_in_progress()

    @contextmanager
    def _store_lock(self):
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.chmod(self._lock_path, FILE_MODE)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _job_pid_path(self, task_id):
        return os.path.join(self._task_dir(task_id), "job.pid")

    def _pid_alive(self, pid):
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _read_job_pid(self, task_id):
        path = self._job_pid_path(task_id)
        if not os.path.isfile(path):
            return None
        try:
            raw = _read_bounded(path, 32).decode("utf-8").strip()
            return int(raw)
        except (ValueError, OSError):
            return None

    def _write_job_pid(self, task_id, pid):
        path = self._job_pid_path(task_id)
        directory = os.path.dirname(path)
        os.makedirs(directory, mode=DIR_MODE, exist_ok=True)
        self._atomic_write(path, ("%s\n" % pid).encode("utf-8"))

    def _clear_job_pid(self, task_id):
        path = self._job_pid_path(task_id)
        try:
            os.unlink(path)
        except FileNotFoundError:
            return

    def _sync_job_pid(self, record):
        if record.stage in IN_PROGRESS_STAGES:
            self._write_job_pid(record.task_id, os.getpid())
        else:
            self._clear_job_pid(record.task_id)

    def job_alive(self, task_id):
        pid = self._read_job_pid(task_id)
        return self._pid_alive(pid) if pid is not None else False

    def _task_dir(self, task_id):
        if not TASK_ID_RE.match(task_id or ""):
            raise ValueError("invalid task id")
        path = os.path.join(self._tasks_dir, task_id)
        real = os.path.realpath(path)
        if not real.startswith(self._tasks_dir + os.sep) and real != self._tasks_dir:
            raise ValueError("path traversal rejected")
        if os.path.lexists(path):
            _reject_symlink_ancestors(path)
        return path

    def _state_path(self, task_id):
        return os.path.join(self._task_dir(task_id), "state.json")

    def _atomic_write(self, path, data_bytes):
        directory = os.path.dirname(path)
        _reject_symlink_ancestors(directory)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
        closed = False
        try:
            _write_all(fd, data_bytes)
            os.fsync(fd)
        except Exception:
            os.close(fd)
            closed = True
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        finally:
            if not closed:
                os.close(fd)
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
        os.chmod(path, FILE_MODE)

    def _recover_in_progress(self):
        if not os.path.isdir(self._tasks_dir):
            return
        with self._store_lock():
            for name in os.listdir(self._tasks_dir):
                if not TASK_ID_RE.match(name):
                    continue
                try:
                    rec = self._load_unlocked(name)
                except Exception:
                    raise ValueError("malformed persisted record %s" % name)
                if rec.stage not in IN_PROGRESS_STAGES:
                    continue
                if self.job_alive(rec.task_id):
                    continue
                rec.stage = STAGE_NEEDS_USER
                rec.last_error = "Recovered after restart; job was not rerun."
                rec.updated_at = utcnow()
                self._save_unlocked(rec)

    def save(self, record):
        with self._store_lock():
            self._save_unlocked(record)

    def _save_unlocked(self, record):
        path_dir = self._task_dir(record.task_id)
        os.makedirs(path_dir, mode=DIR_MODE, exist_ok=True)
        os.chmod(path_dir, DIR_MODE)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        self._atomic_write(self._state_path(record.task_id), payload)
        self._sync_job_pid(record)

    def load(self, task_id):
        return self._load_unlocked(task_id)

    def _load_unlocked(self, task_id):
        path = self._state_path(task_id)
        if not os.path.isfile(path):
            raise FileNotFoundError("unknown task")
        _reject_symlink_ancestors(path)
        raw = _read_bounded(path, MAX_STATE_BYTES)
        data = json.loads(raw.decode("utf-8"))
        rec = TaskRecord.from_dict(data)
        if rec.task_id != task_id:
            raise ValueError("record id mismatch")
        if rec.project != self.project_root:
            raise ValueError("record project mismatch")
        return rec

    def write_artifact(self, task_id, name, content, version=1):
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError("invalid artifact name")
        directory = self._task_dir(task_id)
        filename = "%s.v%s.txt" % (name, version)
        path = os.path.join(directory, filename)
        _reject_symlink_ancestors(directory)
        payload = content.encode("utf-8")
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds bound")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(path, flags, FILE_MODE)
        except FileExistsError:
            raise ValueError("artifact already exists")
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        finally:
            os.close(fd)
        os.chmod(path, FILE_MODE)
        return filename

    def read_artifact(self, task_id, filename):
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("invalid artifact name")
        path = os.path.join(self._task_dir(task_id), filename)
        _reject_symlink_ancestors(path)
        raw = _read_bounded(path, MAX_ARTIFACT_BYTES)
        return raw.decode("utf-8")

    def list_records(self):
        out = []
        for name in os.listdir(self._tasks_dir):
            if not TASK_ID_RE.match(name):
                continue
            try:
                out.append(self.load(name))
            except Exception:
                raise
        return out

    def active_for_project(self):
        from .constants import ACTIVE_RUN_STAGES

        found = []
        for rec in self.list_records():
            if rec.stage in ACTIVE_RUN_STAGES:
                found.append(rec)
        return found
