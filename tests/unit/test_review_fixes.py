from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki import resources as seed_resources
from video_paper_wiki.cli import main
from video_paper_wiki.notes.code_resources import load_code_urls
from video_paper_wiki.notes.encoding import InvalidEncoding
from video_paper_wiki.notes.frozen import FrozenSeedMissing, require_managed_seed
from video_paper_wiki.notes.merge import merge_paper_copy
from video_paper_wiki.notes.section import section_text
from video_paper_wiki.resources import read_schema_text, read_seed_text

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"

MAV = "arxiv-2209.14792"
EXPANDED = "arxiv-2406.18522"
MAV_QUESTION = "没有成对视频-文本数据时，怎样做文生视频？"
REMNANT = "This truncated PDF remnant should not stay on the paper copy."
CUSTOM = "User-authored extra section must survive a re-export."


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _clone_draft(tmp_path: Path, paper_id: str, title: str, claims: list | None = None) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = title
    if claims is not None:
        document["claims"] = claims
    path = tmp_path / f"{paper_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _latin1_note(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"---\ntitle: caf\xe9\n---\n\n## intro\nbody\n")


def test_require_managed_seed_rejects_unknown_ids() -> None:
    try:
        require_managed_seed("fixture-minimal")
    except FrozenSeedMissing as exc:
        assert exc.paper_id == "fixture-minimal"
        assert exc.source == "engine-mvp.json"
    else:
        raise AssertionError("expected FrozenSeedMissing")
    require_managed_seed(MAV)
    require_managed_seed(EXPANDED)


def test_expanded_catalog_paper_clears_remnants_without_inventing(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    draft = _clone_draft(
        tmp_path,
        EXPANDED,
        "ChronoMagic-Bench",
        [
            {
                "claim_text": REMNANT,
                "section": "research_question",
                "core": False,
                "assessment": "provisional",
                "locators": [],
            }
        ],
    )
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    copied = (dest / "papers" / f"{EXPANDED}.md").read_text(encoding="utf-8")
    work = (tmp_path / ".work" / "notes" / f"{EXPANDED}.md").read_text(encoding="utf-8")
    assert section_text(work, "研究问题") == REMNANT
    assert section_text(copied, "研究问题") == ""
    assert REMNANT not in copied
    assert section_text(copied, "证据状态") == "provisional"
    assert network_attempts == []


def _patch_code_urls_seed(monkeypatch, text: str | None) -> None:
    real = read_seed_text

    def _fake(filename: str) -> str | None:
        if filename == "engine-mvp-code-urls.json":
            return text
        return real(filename)

    monkeypatch.setattr("video_paper_wiki.resources.read_seed_text", _fake)


def test_missing_required_overlay_is_fail_closed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("video_paper_wiki.notes.frozen.load_conclusions", lambda: None)
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == MAV
    assert payload["error"]["details"]["source"] == "engine-mvp-conclusions.json"
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_missing_code_urls_seed_is_fail_closed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_code_urls_seed(monkeypatch, None)
    assert load_code_urls() is None
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == MAV
    assert payload["error"]["details"]["source"] == "engine-mvp-code-urls.json"
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_invalid_code_urls_json_is_fail_closed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_code_urls_seed(monkeypatch, "{not-json")
    assert load_code_urls() is None
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["source"] == "engine-mvp-code-urls.json"
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def _latin1_code_urls_seed(tmp_path: Path, monkeypatch) -> Path:
    bad = tmp_path / "docs" / "seed" / "engine-mvp-code-urls.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b'{"code_urls": {}}\n' + bytes([0xE9]))
    real_package = seed_resources._package_text
    real_repo_file = seed_resources._repo_file

    def _package_text(*parts: str) -> str | None:
        if parts and parts[-1] == "engine-mvp-code-urls.json":
            return None
        return real_package(*parts)

    def _repo_file(relative: Path) -> Path | None:
        if Path(relative) == Path("docs") / "seed" / "engine-mvp-code-urls.json":
            return bad
        return real_repo_file(relative)

    monkeypatch.setattr("video_paper_wiki.resources._package_text", _package_text)
    monkeypatch.setattr("video_paper_wiki.resources._repo_file", _repo_file)
    return bad


def test_latin1_code_urls_seed_is_fail_closed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    _latin1_code_urls_seed(tmp_path, monkeypatch)
    assert load_code_urls() is None
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == MAV
    assert payload["error"]["details"]["source"] == "engine-mvp-code-urls.json"
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "UnicodeDecodeError" not in captured.out
    assert "UnicodeDecodeError" not in captured.err
    assert "InvalidEncoding" not in captured.out
    assert "InvalidEncoding" not in captured.err
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_empty_code_urls_object_still_exports(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_code_urls_seed(monkeypatch, '{"code_urls": {}}\n')
    assert load_code_urls() == {}
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    assert (dest / "papers" / f"{MAV}.md").is_file()
    assert (tmp_path / ".work" / "notes" / f"{MAV}.md").is_file()
    assert network_attempts == []


def test_review_export_does_not_open_pdf(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)

    def _boom(*_args, **_kwargs):
        raise AssertionError("vault write path must not read a PDF")

    monkeypatch.setattr("video_paper_wiki.parse.pypdf_local.parse_pdf_to_draft_fields", _boom)
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    assert (dest / "papers" / f"{MAV}.md").is_file()
    assert network_attempts == []


def test_merge_preserves_unknown_h2_and_owned_yaml() -> None:
    existing = (
        "---\n"
        "title: Old Title\n"
        "paper_id: arxiv-2209.14792\n"
        "tags: [keep-me]\n"
        "arxiv_id: 0000.00000\n"
        "year: 1999\n"
        "topics: []\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "old conclusion\n"
        "\n"
        "## 自定义\n"
        "\n"
        f"{CUSTOM}\n"
        "\n"
        "## 研究问题\n"
        "\n"
        "old question\n"
    )
    rendered = (
        "---\n"
        "title: Make-A-Video\n"
        "paper_id: arxiv-2209.14792\n"
        "arxiv_id: 2209.14792\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "related: [arxiv-2204.03458]\n"
        "backlinks: [arxiv-2311.15127]\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "new conclusion\n"
        "\n"
        "## 研究问题\n"
        "\n"
        f"{MAV_QUESTION}\n"
    )
    merged = merge_paper_copy(existing, rendered)
    yaml, body = merged.split("---", 2)[1], merged.split("---", 2)[2]
    assert "title: Make-A-Video" in yaml
    assert "tags: [keep-me]" in yaml
    assert "arxiv_id: 2209.14792" in yaml
    assert "year: 2022" in yaml
    assert "1999" not in yaml
    assert "Old Title" not in yaml
    assert section_text(merged, "一句话结论") == "new conclusion"
    assert section_text(merged, "研究问题") == MAV_QUESTION
    assert section_text(merged, "自定义") == CUSTOM
    assert CUSTOM in body


def test_merge_replaces_system_related_links_keeps_custom_h2() -> None:
    existing = (
        "---\n"
        "title: MAGVIT\n"
        "paper_id: arxiv-2212.05199\n"
        "related: [arxiv-2312.03541, arxiv-2406.08119]\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "old conclusion\n"
        "\n"
        "## 自定义\n"
        "\n"
        f"{CUSTOM}\n"
        "\n"
        "## 主题\n"
        "\n"
        "[视频 tokenizer](../wiki/tokenization.md)\n"
        "\n"
        "## 相关论文\n"
        "\n"
        "[MAGVIT-v2](./arxiv-2312.03541.md) (2023)\n"
        "[OmniTokenizer](./arxiv-2406.08119.md) (2024)\n"
    )
    rendered = (
        "---\n"
        "title: MAGVIT\n"
        "paper_id: arxiv-2212.05199\n"
        "related: [arxiv-2310.05737, arxiv-2406.09399]\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "new conclusion\n"
        "\n"
        "## 主题\n"
        "\n"
        "[视频 tokenizer](../wiki/tokenization.md)\n"
        "\n"
        "## 相关论文\n"
        "\n"
        "[MAGVIT-v2](./arxiv-2310.05737.md) (2023)\n"
        "[OmniTokenizer](./arxiv-2406.09399.md) (2024)\n"
    )
    merged = merge_paper_copy(existing, rendered)
    related = section_text(merged, "相关论文")
    assert related is not None
    assert "arxiv-2310.05737" in related
    assert "arxiv-2406.09399" in related
    assert "arxiv-2312.03541" not in related
    assert "arxiv-2406.08119" not in related
    assert "arxiv-2312.03541" not in merged
    assert "arxiv-2406.08119" not in merged
    assert section_text(merged, "自定义") == CUSTOM
    assert section_text(merged, "一句话结论") == "new conclusion"


def test_review_export_merges_existing_note(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    capsys.readouterr()
    copied = dest / "papers" / f"{MAV}.md"
    original = copied.read_text(encoding="utf-8")
    mutated = original.replace("---\n", "---\ntags: [keep-me]\n", 1)
    mutated = mutated + "\n## 自定义\n\n" + CUSTOM + "\n"
    copied.write_text(mutated, encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    text = copied.read_text(encoding="utf-8")
    assert "tags: [keep-me]" in text.split("---", 2)[1]
    assert section_text(text, "自定义") == CUSTOM
    assert section_text(text, "研究问题") == MAV_QUESTION
    work = (tmp_path / ".work" / "notes" / f"{MAV}.md").read_text(encoding="utf-8")
    assert "自定义" not in work
    assert network_attempts == []


def test_review_export_refreshes_related_trailer_ids(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    magvit = "arxiv-2212.05199"
    draft = _clone_draft(tmp_path, magvit, "MAGVIT")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    capsys.readouterr()
    copied = dest / "papers" / f"{magvit}.md"
    mutated = copied.read_text(encoding="utf-8")
    mutated = mutated.replace("arxiv-2310.05737", "arxiv-2312.03541")
    mutated = mutated.replace("arxiv-2406.09399", "arxiv-2406.08119")
    mutated = mutated + "\n## 自定义\n\n" + CUSTOM + "\n"
    copied.write_text(mutated, encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    text = copied.read_text(encoding="utf-8")
    related = section_text(text, "相关论文")
    assert related is not None
    assert "arxiv-2310.05737" in related
    assert "arxiv-2406.09399" in related
    assert "arxiv-2312.03541" not in related
    assert "arxiv-2406.08119" not in related
    assert section_text(text, "自定义") == CUSTOM
    work = (tmp_path / ".work" / "notes" / f"{magvit}.md").read_text(encoding="utf-8")
    assert "## 相关论文" not in work
    assert "## 主题" not in work
    assert network_attempts == []


def test_resources_loader_finds_seed_and_schema() -> None:
    seed = read_seed_text("engine-mvp.json")
    assert seed is not None
    assert '"papers"' in seed
    schema = read_schema_text("video-paper-wiki.paper-analysis-draft.v1.schema.json")
    assert schema is not None
    assert "paper-analysis-draft.v1" in schema
    urls = read_seed_text("engine-mvp-code-urls.json")
    assert urls is not None
    assert '"code_urls"' in urls


def test_repo_seed_latin1_raises_invalid_encoding(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "latin1-seed.json"
    bad.write_bytes(b'{"papers": []}\n' + bytes([0xE9]))
    monkeypatch.setattr("video_paper_wiki.resources._package_text", lambda *_parts: None)
    monkeypatch.setattr("video_paper_wiki.resources._repo_file", lambda _relative: bad)
    try:
        read_seed_text("engine-mvp.json")
    except InvalidEncoding as exc:
        assert exc.path == bad
    else:
        raise AssertionError("expected InvalidEncoding")


def _assert_invalid_encoding(code: int, payload: dict, command: str, captured, path: Path) -> None:
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] == command
    assert payload["error"]["code"] == "INVALID_ENCODING"
    assert payload["error"]["details"]["path"] == path.as_posix()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "UnicodeDecodeError" not in captured.out
    assert "UnicodeDecodeError" not in captured.err


def test_notes_commands_invalid_encoding_json_envelope(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    bad = notes / "papers" / "arxiv-2408.06072.md"
    _latin1_note(bad)
    cases = [
        (["vault", "grep", "--vault", str(notes), "body"], "vault.grep"),
        (["vault", "stat", "--vault", str(notes)], "vault.stat"),
        (["vault", "list", "--vault", str(notes)], "vault.list"),
        (["vault", "show", "--vault", str(notes), "arxiv-2408.06072"], "vault.show"),
        (["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "方法"], "vault.section"),
        (["vault", "headings", "--vault", str(notes), "arxiv-2408.06072"], "vault.headings"),
        (["vault", "doctor", "--vault", str(notes)], "vault.doctor"),
    ]
    for argv, command in cases:
        code = main(argv)
        captured = capsys.readouterr()
        payload = json.loads(captured.out.strip())
        _assert_invalid_encoding(code, payload, command, captured, bad)
        assert bad.exists()
    assert network_attempts == []


def test_review_export_existing_note_invalid_encoding(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    bad = dest / "papers" / f"{MAV}.md"
    _latin1_note(bad)
    draft = _clone_draft(tmp_path, MAV, "Make-A-Video")
    before = bad.read_bytes()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    _assert_invalid_encoding(code, payload, "review.export", captured, bad)
    assert bad.read_bytes() == before
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []
