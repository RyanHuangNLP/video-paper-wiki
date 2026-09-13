import json
import os
from pathlib import Path

import pytest

from tests.preview_fixture import NOW, preview_flow
from video_paper_wiki import staging
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.paper_preview import decide_paper, list_papers, make_request, request_paper
from video_paper_wiki_research.preview_contracts import saved_bytes, seal
from video_paper_wiki_research.preview_storage import open_preview_session, read_input


def test_idempotent_create_only_and_session_path(checkout):
    first = request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    assert request_paper(arxiv="2408.06072v2", session="preview", now=NOW) == first
    path = Path(first["request"]["path"])
    assert path.parent == checkout / ".work/research/preview/preview-v1/requests"
    with open_preview_session("preview") as store:
        with pytest.raises(ResearchError):
            store.load_path(path, "metadata")
        with pytest.raises(ResearchError):
            store.load_path(checkout / "copied.json", "request")


@pytest.mark.parametrize("name", ["../escape", "", "/absolute", "a/b", "x" * 65, "中", ".hidden"])
def test_session_names_refused_before_writes(checkout, name):
    with pytest.raises(ResearchError):
        request_paper(arxiv="2408.06072", session=name, now=NOW)
    assert not (checkout / ".work").exists()


@pytest.mark.parametrize("level", ["research", "session", "root", "family"])
@pytest.mark.parametrize("error_exit", [False, True])
def test_persistent_named_replacement_dominates(checkout, level, error_exit):
    request_paper(arxiv="2408.06072", session="preview", now=NOW)
    root = checkout / ".work/research/preview/preview-v1"
    target = {"research": root.parent.parent, "session": root.parent, "root": root, "family": root / "requests"}[level]
    with pytest.raises(staging.StagingError) as caught:
        with open_preview_session("preview"):
            target.rename(target.with_name(target.name + "-original"))
            target.mkdir()
            if error_exit:
                raise ResearchError("ARXIV_METADATA_INCOMPLETE", "synthetic parse failure")
    assert caught.value.code == "WORK_PATH_UNSAFE"


def test_scan_error_replacement_is_checked(checkout, monkeypatch):
    request_paper(arxiv="2408.06072", session="preview", now=NOW)
    original = staging._read_regular_file_at_bounded_identity
    fired = False
    def replace(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            root = checkout / ".work/research/preview/preview-v1"
            root.rename(root.with_name("preview-old"))
            root.mkdir()
            raise ResearchError("ARTIFACT_INVALID", "synthetic read refusal")
        return original(*args, **kwargs)
    monkeypatch.setattr(staging, "_read_regular_file_at_bounded_identity", replace)
    with pytest.raises(staging.StagingError) as caught:
        list_papers(session="preview")
    assert caught.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("entry", ["symlink", "hardlink", "fifo", "directory", "unexpected"])
def test_unsafe_orphan_entry_refused(checkout, entry):
    result = request_paper(arxiv="2408.06072", session="preview", now=NOW)
    path = Path(result["request"]["path"])
    other = path.with_name("0" * 64 + ".json")
    if entry == "symlink":
        other.symlink_to(path)
    elif entry == "hardlink":
        os.link(path, other)
    elif entry == "fifo":
        os.mkfifo(other)
    elif entry == "directory":
        other.mkdir()
    else:
        path.with_name("notes.txt").write_text("unexpected")
    with pytest.raises(staging.StagingError) as caught:
        list_papers(session="preview")
    assert caught.value.code == "WORK_PATH_UNSAFE"


def test_partial_failure_leaves_only_valid_request(checkout, monkeypatch):
    from tests.preview_fixture import metadata_flow
    original = staging._atomic_install
    def fail_observation(*args, **kwargs):
        if kwargs["target"].parent.name == "observations":
            raise ResearchError("ARTIFACT_INVALID", "synthetic install interruption")
        return original(*args, **kwargs)
    monkeypatch.setattr(staging, "_atomic_install", fail_observation)
    with pytest.raises(ResearchError):
        metadata_flow(checkout)
    with open_preview_session("preview") as store:
        assert len(store.all("request")) == 1
        assert all(store.all(kind) == [] for kind in ("observation", "metadata", "preview", "decision"))


def test_decision_gap_refuses_list(checkout):
    result = preview_flow(checkout)
    for number in (1, 2):
        decide_paper(session="preview", preview=result["preview"]["path"], action="later", event_id=f"event-{number}",
                     user_text="Fixture", source="fixture", recorded_at=NOW)
    root = Path(result["preview"]["path"]).parent.parent
    (root / "decisions/000001.json").unlink()
    with pytest.raises(ResearchError) as caught:
        list_papers(session="preview")
    assert caught.value.code in {"DECISION_INVALID", "ARTIFACT_BINDING_MISMATCH"}


def test_family_limit(checkout):
    request_paper(arxiv="2408.06072", session="preview", now=NOW)
    root = checkout / ".work/research/preview/preview-v1/requests"
    # Populate canonical independent requests directly to test the real bounded scan.
    for number in range(256):
        document = make_request(f"2408.{number:05d}")
        (root / (document["content_sha256"] + ".json")).write_bytes(saved_bytes(document))
    with pytest.raises(ResearchError) as caught:
        list_papers(session="preview")
    assert caught.value.code == "SESSION_LIMIT_EXCEEDED"


@pytest.mark.parametrize("error_exit", [False, True])
def test_local_input_parent_and_file_retained(checkout, error_exit):
    parent = checkout / "input"
    parent.mkdir()
    path = parent / "data.json"
    path.write_bytes(b"{}\n")
    with pytest.raises(Exception) as caught:
        with read_input(path):
            parent.rename(checkout / "old-input")
            parent.mkdir()
            path.write_bytes(b"{}\n")
            if error_exit:
                raise ResearchError("ARTIFACT_INVALID", "synthetic parse refusal")
    assert caught.value.code == "WORK_PATH_UNSAFE"


def test_input_ancestor_replaced_while_same_parent_moves(checkout):
    ancestor = checkout / "ancestor"
    parent = ancestor / "input"
    parent.mkdir(parents=True)
    path = parent / "data.json"
    path.write_bytes(b"{}")
    with pytest.raises(staging.StagingError) as caught:
        with read_input(path):
            ancestor.rename(checkout / "old-ancestor")
            ancestor.mkdir()
            (checkout / "old-ancestor/input").rename(parent)
    assert caught.value.code == "WORK_PATH_UNSAFE"


def test_maximum_decision_chain_and_257th_refusal(checkout):
    from video_paper_wiki_research.preview_contracts import reference
    result = preview_flow(checkout)
    root = Path(result["preview"]["path"]).parent.parent / "decisions"
    previous = None
    for sequence in range(1, 257):
        decision = seal("decision", {"preview": result["preview"]["reference"], "sequence": sequence,
                                     "previous": previous, "action": "later", "selected_version": None,
                                     "user_record": {"event_id": f"event-{sequence}", "text": "Fixture retained chain",
                                                     "source": "fixture", "recorded_at": NOW}})
        (root / f"{sequence:06d}.json").write_bytes(saved_bytes(decision))
        previous = reference(decision)
    assert list_papers(session="preview")["decision_count"] == 256
    with pytest.raises(ResearchError) as caught:
        decide_paper(session="preview", preview=result["preview"]["path"], action="skip", event_id="event-257",
                     user_text="Fixture", source="fixture")
    assert caught.value.code == "SESSION_LIMIT_EXCEEDED"


@pytest.mark.parametrize("replace_directory", [False, True])
def test_competing_decision_writer_preserves_conflict_and_named_safety(checkout, monkeypatch, replace_directory):
    from video_paper_wiki_research.preview_contracts import reference
    result = preview_flow(checkout)
    rival = seal("decision", {"preview": result["preview"]["reference"], "sequence": 1, "previous": None,
                              "action": "skip", "selected_version": None,
                              "user_record": {"event_id": "rival", "text": "Fixture competing choice",
                                              "source": "fixture", "recorded_at": NOW}})
    original = staging._atomic_install
    fired = False
    def install(*args, **kwargs):
        nonlocal fired
        if kwargs["target"].parent.name == "decisions" and not fired:
            fired = True
            rival_args = (*args[:3], saved_bytes(rival))
            original(*rival_args, **kwargs)
            if replace_directory:
                target = kwargs["target"].parent
                target.rename(target.with_name("replaced-decisions"))
                target.mkdir()
        return original(*args, **kwargs)
    monkeypatch.setattr(staging, "_atomic_install", install)
    with pytest.raises((ResearchError, staging.StagingError)) as caught:
        decide_paper(session="preview", preview=result["preview"]["path"], action="later", event_id="primary",
                     user_text="Fixture", source="fixture", recorded_at=NOW)
    assert caught.value.code == ("WORK_PATH_UNSAFE" if replace_directory else "STAGING_CONFLICT")
    if not replace_directory:
        assert caught.value.exit_code == 75
        listed = list_papers(session="preview")
        assert listed["decision_count"] == 1 and listed["previews"][0]["state"] == "skip"
        assert listed["previews"][0]["decision"]["reference"] == reference(rival)
