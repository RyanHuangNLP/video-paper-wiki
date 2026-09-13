from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.markdown_source_fixture import LIGHT_ID, light_source, prepared_source
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.markdown_source_io import markdown_slots
from video_paper_wiki_research.formal_source import plan_markdown_source, prepare_markdown_source


@pytest.mark.parametrize("kind", ["traversal", "symlink", "hardlink", "fifo"])
def test_original_source_paths_refuse_unsafe_spelling_and_files(checkout, kind):
    workspace, md, _ = light_source(checkout)
    if kind == "traversal":
        workspace = str(workspace) + "/../light-library"
    else:
        original = md.with_suffix(".original")
        md.rename(original)
        if kind == "symlink":
            md.symlink_to(original)
        elif kind == "hardlink":
            os.link(original, md)
        else:
            os.mkfifo(md)
    with pytest.raises(ContractError) as err:
        plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="unsafe")
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert not (checkout / ".work/unsafe").exists()


@pytest.mark.parametrize("name,kind", [("orphan", "file"), ("empty", "directory"), ("b" * 64 + ".md", "file")])
def test_markdown_complete_set_rejects_orphans(checkout, name, kind):
    planned, _, _ = prepared_source(checkout)
    path = Path(planned["plan_path"]).parent / name
    path.mkdir() if kind == "directory" else path.write_bytes(b"orphan")
    with pytest.raises(ContractError) as err:
        prepare_markdown_source(plan=planned["plan_path"], approval_ref=checkout / ".work/fixture-approval.json")
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("child_fails", [False, True])
def test_same_bytes_named_file_replacement_overrides_all_exits(checkout, monkeypatch, child_fails):
    import video_paper_wiki_research.formal_source as module
    workspace, md, _ = light_source(checkout)
    original = module._observe

    def replace(*args, **kwargs):
        result = original(*args, **kwargs)
        replacement = md.with_suffix(".replacement")
        replacement.write_bytes(md.read_bytes())
        replacement.replace(md)
        if child_fails:
            raise ContractError("CHILD_FAILURE", "synthetic child refusal", {})
        return result

    monkeypatch.setattr(module, "_observe", replace)
    with pytest.raises(ContractError) as err:
        module.plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="race")
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("child_fails", [False, True])
def test_missing_fixed_request_appearance_is_retained(checkout, child_fails):
    workspace, *_ = light_source(checkout)
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="race")
    with pytest.raises(ContractError) as err:
        with markdown_slots("race", create=False) as slots:
            (slots.path / "request.json").write_bytes(b"{}")
            if child_fails:
                raise ContractError("CHILD_FAILURE", "synthetic", {})
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("child_fails", [False, True])
def test_staging_directory_replacement_is_retained(checkout, child_fails):
    prepared_source(checkout)
    with pytest.raises(ContractError) as err:
        with markdown_slots("md-capture", create=False) as slots:
            moved = slots.path.with_name("old-markdown-source")
            slots.path.rename(moved)
            slots.path.mkdir()
            for file in moved.iterdir():
                (slots.path / file.name).write_bytes(file.read_bytes())
            if child_fails:
                raise ContractError("CHILD_FAILURE", "synthetic", {})
    assert err.value.code == "WORK_PATH_UNSAFE"
