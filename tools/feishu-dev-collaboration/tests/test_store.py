import json
import os
import stat
import tempfile
import unittest
import uuid

from cli_bridge.constants import DIR_MODE
from cli_bridge.store import TaskStore, new_task_id
from tests.helpers import make_engine


class StoreTests(unittest.TestCase):
    def test_rejects_data_inside_project(self):
        root = os.path.realpath(tempfile.mkdtemp())
        project = os.path.join(root, "project")
        os.makedirs(project)
        data = os.path.join(project, "data")
        with self.assertRaises(ValueError):
            TaskStore(data, project)

    def test_rejects_symlink_tasks_dir(self):
        root = os.path.realpath(tempfile.mkdtemp())
        data = os.path.join(root, "data")
        project = os.path.join(root, "project")
        os.makedirs(data)
        os.makedirs(project)
        os.symlink(project, os.path.join(data, "tasks"))
        with self.assertRaises(ValueError):
            TaskStore(data, project)

    def test_rejects_path_escape_task_id(self):
        engine, _, _ = make_engine()
        with self.assertRaises(ValueError):
            engine.store.load("../" + "a" * 30)

    def test_malformed_record_not_idle(self):
        engine, data, project = make_engine()
        task_id = new_task_id()
        path = os.path.join(data, "tasks", task_id)
        os.makedirs(path, mode=DIR_MODE)
        with open(os.path.join(path, "state.json"), "w") as fh:
            fh.write("{not json")
        with self.assertRaises(Exception):
            TaskStore(data, project)

    def test_id_and_project_mismatch(self):
        engine, data, project = make_engine()
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        path = os.path.join(data, "tasks", rec.task_id, "state.json")
        with open(path) as fh:
            payload = json.load(fh)
        payload["task_id"] = uuid.uuid4().hex
        with open(path, "w") as fh:
            json.dump(payload, fh)
        with self.assertRaises(ValueError):
            engine.store.load(rec.task_id)

    def test_create_once_artifact(self):
        engine, _, _ = make_engine()
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        name = engine.store.write_artifact(rec.task_id, "prd", "hello", version=1)
        with self.assertRaises(ValueError):
            engine.store.write_artifact(rec.task_id, "prd", "other", version=1)
        self.assertEqual(engine.store.read_artifact(rec.task_id, name), "hello")

    def test_requirement_metacharacters_are_data(self):
        engine, _, _ = make_engine()
        text = "fix; rm -rf / | wget http://x && echo $(whoami)"
        rec, _ = engine.start_draft(text, "m1", "openid-owner", "chat-owner")
        self.assertEqual(rec.requirement, text)

    def test_live_job_pid_not_recovered(self):
        import subprocess

        engine, data, project = make_engine()
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        proc = subprocess.Popen(["sleep", "30"])
        try:
            engine.store._write_job_pid(rec.task_id, proc.pid)
            store2 = TaskStore(data, project)
            recovered = store2.load(rec.task_id)
            self.assertEqual(recovered.stage, "drafting")
        finally:
            proc.kill()
            proc.wait()
