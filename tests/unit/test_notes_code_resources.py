from __future__ import annotations

from tests.support import make_checkout, plant_blob, work_review

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.identity import claim_id
from video_paper_wiki.notes.code_resources import (
    apply_clean_code_resources,
    is_http_url,
    load_code_urls,
    valid_http_urls,
)
from video_paper_wiki.notes.section import section_text
from video_paper_wiki.resources import read_seed_text as _real_seed

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

MAV = "arxiv-2209.14792"
MAV_CANON = "arxiv:2209.14792"
MAV_QUESTION = "没有成对视频-文本数据时，怎样做文生视频？"
MAV_SENTENCE = "用图像扩散先验做文生视频，不必成对的视频-文本数据。"
MAV_METHOD = "先训图像扩散，再加时空卷积和注意力，用图像-文本对齐做文生视频。"
MAV_ARCH = "图像 U-Net 加上伪 3D 时空卷积和时空注意力。"
MAV_TRAIN = "先用图像-文本数据训图像扩散，再用无标签视频学时空模块。"
MAV_EXP = "无成对视频-文本数据也能做出有竞争力的文生视频。"
MAV_LIMIT = "没有成对视频-文本，细粒度文本控制偏弱。"
MAV_ASSOC = "证明图像先验可以迁到视频，后面 SVD、DynamiCrafter 也走这条路。"
REMNANT = "This truncated PDF remnant should not stay on the paper copy."
CODE = "https://example.com/make-a-video"
CODE_DOT = "https://example.com/make-a-video."
CODE_HTTP = "http://example.com/make-a-video"
FAKE_GH = "Code is available at github.com/someone/make-a-video"
EVIDENCE = "provisional; local pypdf extract"
RELATED_LINKS = "[CogVideoX](./arxiv-2408.06072.md) (2024)"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _assert_urls_only(body: str | None) -> None:
    text = "" if body is None else body
    for line in text.splitlines():
        if not line.strip():
            continue
        assert line.startswith("http://") or line.startswith("https://")


def test_valid_http_urls_offline_scheme_and_netloc() -> None:
    assert valid_http_urls(
        [
            CODE,
            CODE_HTTP,
            "ftp://example.com/x",
            "https://",
            "not-a-url",
            "github.com/someone/make-a-video",
            CODE,
        ]
    ) == [CODE, CODE_HTTP]


def test_is_http_url_urlsplit_value_error_is_invalid() -> None:
    assert is_http_url("http://[") is False
    assert valid_http_urls(["http://[", CODE, "https://["]) == [CODE]


def test_load_code_urls_legal_empty_object() -> None:
    assert load_code_urls() == {}


def test_load_code_urls_missing_file_is_none(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.resources.read_seed_text",
        lambda filename: None if filename == "engine-mvp-code-urls.json" else _real_seed(filename),
    )
    assert load_code_urls() is None


def test_load_code_urls_invalid_json_is_none(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.resources.read_seed_text",
        lambda filename: "{" if filename == "engine-mvp-code-urls.json" else _real_seed(filename),
    )
    assert load_code_urls() is None


def test_load_code_urls_not_an_object_is_none(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.resources.read_seed_text",
        lambda filename: "[]" if filename == "engine-mvp-code-urls.json" else _real_seed(filename),
    )
    assert load_code_urls() is None


def test_load_code_urls_latin1_is_none(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "docs" / "seed" / "engine-mvp-code-urls.json"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b'{"code_urls": {}}\n' + bytes([0xE9]))
    from video_paper_wiki.notes.encoding import read_utf8

    def _seed(filename: str) -> str | None:
        if filename == "engine-mvp-code-urls.json":
            return read_utf8(bad)
        return _real_seed(filename)

    monkeypatch.setattr("video_paper_wiki.resources.read_seed_text", _seed)
    assert load_code_urls() is None


def test_apply_keeps_urls_drops_remnants(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.notes.code_resources.load_code_urls",
        lambda: {MAV: [CODE, CODE_HTTP]},
    )
    text = (
        "---\n"
        "title: Make-A-Video\n"
        "paper_id: arxiv-2209.14792\n"
        "related: [arxiv-2408.06072]\n"
        "backlinks: [arxiv-2311.15127]\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        f"{MAV_SENTENCE}\n"
        "\n"
        "## 研究问题\n"
        "\n"
        f"{MAV_QUESTION}\n"
        "\n"
        "## 方法\n"
        "\n"
        f"{MAV_METHOD}\n"
        "\n"
        "## 表示与架构\n"
        "\n"
        f"{MAV_ARCH}\n"
        "\n"
        "## 训练与数据\n"
        "\n"
        f"{MAV_TRAIN}\n"
        "\n"
        "## 实验与结果\n"
        "\n"
        f"{MAV_EXP}\n"
        "\n"
        "## 局限\n"
        "\n"
        f"{MAV_LIMIT}\n"
        "\n"
        "## 代码与资源\n"
        "\n"
        f"{REMNANT}\n"
        f"{CODE_DOT}\n"
        f"{CODE_HTTP}\n"
        f"{FAKE_GH}\n"
        "\n"
        "## 证据状态\n"
        "\n"
        f"{EVIDENCE}\n"
        "\n"
        "## 关联\n"
        "\n"
        f"{MAV_ASSOC}\n"
        "\n"
        "## 相关论文\n"
        "\n"
        f"{RELATED_LINKS}\n"
    )
    yaml = text.split("---", 2)[1]
    out = apply_clean_code_resources(text, MAV)
    assert section_text(out, "代码与资源") == f"{CODE}\n{CODE_HTTP}"
    assert REMNANT not in out
    assert FAKE_GH not in out
    assert "github.com/someone/make-a-video" not in out
    assert CODE_DOT not in out
    assert section_text(out, "一句话结论") == MAV_SENTENCE
    assert section_text(out, "研究问题") == MAV_QUESTION
    assert section_text(out, "方法") == MAV_METHOD
    assert section_text(out, "表示与架构") == MAV_ARCH
    assert section_text(out, "训练与数据") == MAV_TRAIN
    assert section_text(out, "实验与结果") == MAV_EXP
    assert section_text(out, "局限") == MAV_LIMIT
    assert section_text(out, "证据状态") == EVIDENCE
    assert section_text(out, "关联") == MAV_ASSOC
    assert section_text(out, "相关论文") == RELATED_LINKS
    assert out.split("---", 2)[1] == yaml
    assert "## 代码与资源\n\n" + CODE + "\n" + CODE_HTTP + "\n\n## 证据状态" in out


def test_apply_empties_section_when_no_url() -> None:
    text = (
        "## 代码与资源\n"
        "\n"
        f"{REMNANT}\n"
        f"{FAKE_GH}\n"
        "\n"
        "## 证据状态\n"
        "\n"
        f"{EVIDENCE}\n"
    )
    out = apply_clean_code_resources(text, MAV)
    assert section_text(out, "代码与资源") == ""
    assert "## 代码与资源\n\n## 证据状态" in out
    assert section_text(out, "证据状态") == EVIDENCE
    assert REMNANT not in out
    assert FAKE_GH not in out


def test_apply_skips_missing_heading() -> None:
    remnant = f"# title\n\n{REMNANT}\n"
    assert apply_clean_code_resources(remnant, MAV) == remnant
    assert "## 代码与资源" not in apply_clean_code_resources(remnant, MAV)


def test_review_export_strips_vault_code_keeps_work_note(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV_CANON
    document["title"] = "Make-A-Video"
    document["claims"] = [
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", REMNANT),
            "claim_text": REMNANT,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", CODE_DOT),
            "claim_text": CODE_DOT,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", FAKE_GH),
            "claim_text": FAKE_GH,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", EVIDENCE),
            "claim_text": EVIDENCE,
            "section": "evidence_status",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
    ]
    draft = tmp_path / "mav.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    copied = work_review(tmp_path, "b1")
    assert payload["data"]["path"] == copied.as_posix()
    assert "vault_path" not in payload["data"]
    copied_text = copied.read_text(encoding="utf-8")
    work_text = copied_text
    yaml = copied_text.split("---", 2)[1]
    assert section_text(copied_text, "代码与资源") == ""
    assert REMNANT not in copied_text
    assert FAKE_GH not in copied_text
    assert CODE not in copied_text
    assert "github.com/someone/make-a-video" not in copied_text
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert section_text(copied_text, "研究问题") == MAV_QUESTION
    assert section_text(copied_text, "方法") == MAV_METHOD
    assert section_text(copied_text, "表示与架构") == MAV_ARCH
    assert section_text(copied_text, "训练与数据") == MAV_TRAIN
    assert section_text(copied_text, "实验与结果") == MAV_EXP
    assert section_text(copied_text, "局限") == MAV_LIMIT
    assert section_text(copied_text, "关联") == MAV_ASSOC
    assert section_text(copied_text, "证据状态") == "provisional"
    assert "local pypdf extract" not in copied_text.split("## 证据状态", 1)[1].split("##", 1)[0]
    assert "related:" in yaml
    assert "backlinks:" in yaml
    assert "## 主题" in copied_text
    assert "## 相关论文" in copied_text
    assert network_attempts == []


def test_review_export_empties_code_when_only_remnant(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV_CANON
    document["title"] = "Make-A-Video"
    document["claims"] = [
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", REMNANT),
            "claim_text": REMNANT,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_id": claim_id(f"paper:{MAV_CANON}", FAKE_GH),
            "claim_text": FAKE_GH,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
    ]
    draft = tmp_path / "mav.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 0
    _stdout_json(capsys)
    copied_text = work_review(tmp_path, "b1").read_text(encoding="utf-8")
    assert section_text(copied_text, "代码与资源") == ""
    assert REMNANT not in copied_text
    assert FAKE_GH not in copied_text
    assert "https://github.com" not in copied_text
    assert section_text(copied_text, "关联") == MAV_ASSOC
    assert network_attempts == []


def test_ingest_writes_url_only_code_on_vault_copy(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV_CANON
    document["title"] = "Make-A-Video"
    draft = tmp_path / "mav-ingest.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    copied_text = work_review(tmp_path, "b1").read_text(encoding="utf-8")
    work_text = copied_text
    _assert_urls_only(section_text(copied_text, "代码与资源"))
    assert "github.com" not in (section_text(copied_text, "代码与资源") or "")
    assert section_text(copied_text, "关联") == MAV_ASSOC
    assert section_text(copied_text, "局限") == MAV_LIMIT
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert "## 代码与资源" in copied_text
    assert "## 代码与资源" in work_text
    assert network_attempts == []
