from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes.clear_draft import apply_empty_draft_sections
from video_paper_wiki.notes.section import section_text

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

MAV = "arxiv-2209.14792"
MAV_SENTENCE = "用图像扩散先验做文生视频，不必成对的视频-文本数据。"
MAV_QUESTION = "没有成对视频-文本数据时，怎样做文生视频？"
MAV_METHOD = "先训图像扩散，再加时空卷积和注意力，用图像-文本对齐做文生视频。"
MAV_ARCH = "图像 U-Net 加上伪 3D 时空卷积和时空注意力。"
REMNANT = "This truncated PDF remnant should not stay on the paper copy."
METHOD = "The model uses a diffusion transformer."
CODE = "https://example.com/make-a-video"
EVIDENCE = "provisional; local pypdf extract"
CLEAR = (
    "研究问题",
    "方法",
    "表示与架构",
    "训练与数据",
    "实验与结果",
    "局限",
    "关联",
)
KEEP = (
    "一句话结论",
    "代码与资源",
    "证据状态",
    "主题",
    "相关论文",
)


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_apply_empties_listed_sections_keeps_others() -> None:
    text = (
        "---\n"
        "title: Make-A-Video\n"
        "paper_id: arxiv-2209.14792\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        f"{MAV_SENTENCE}\n"
        "\n"
        "## 研究问题\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 方法\n"
        "\n"
        f"{METHOD}\n"
        "\n"
        "## 表示与架构\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 训练与数据\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 实验与结果\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 局限\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 代码与资源\n"
        "\n"
        f"{CODE}\n"
        "\n"
        "## 证据状态\n"
        "\n"
        f"{EVIDENCE}\n"
        "\n"
        "## 关联\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 主题\n"
        "\n"
        "[视频扩散](../wiki/video-diffusion.md)\n"
        "\n"
        "## 相关论文\n"
        "\n"
        "[CogVideoX](./arxiv-2408.06072.md) (2024)\n"
    )
    yaml = text.split("---", 2)[1]
    out = apply_empty_draft_sections(text)
    assert out.split("---", 2)[1] == yaml
    assert section_text(out, "一句话结论") == MAV_SENTENCE
    assert section_text(out, "代码与资源") == CODE
    assert section_text(out, "证据状态") == EVIDENCE
    assert section_text(out, "主题") == "[视频扩散](../wiki/video-diffusion.md)"
    assert section_text(out, "相关论文") == "[CogVideoX](./arxiv-2408.06072.md) (2024)"
    for heading in CLEAR:
        assert section_text(out, heading) == ""
        assert f"## {heading}\n\n## " in out or heading == "关联"
    assert "## 关联\n\n## 主题" in out
    assert REMNANT not in out
    assert METHOD not in out


def test_apply_does_not_add_missing_headings() -> None:
    text = f"# title\n\n{REMNANT}\n"
    assert apply_empty_draft_sections(text) == text
    assert "## 方法" not in apply_empty_draft_sections(text)


def test_review_export_clears_vault_keeps_work_and_frozen_conclusion(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV
    document["title"] = "Make-A-Video"
    document["claims"] = [
        {
            "claim_text": REMNANT,
            "section": "one_sentence_conclusion",
            "core": True,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_text": METHOD,
            "section": "method",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_text": CODE,
            "section": "code_resources",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_text": EVIDENCE,
            "section": "evidence_status",
            "core": False,
            "assessment": "provisional",
            "locators": [],
        },
    ]
    draft = tmp_path / "mav.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    work = tmp_path / ".work" / "notes" / f"{MAV}.md"
    copied = dest / "papers" / f"{MAV}.md"
    assert payload["data"]["path"] == work.as_posix()
    assert payload["data"]["vault_path"] == copied.as_posix()
    work_text = work.read_text(encoding="utf-8")
    copied_text = copied.read_text(encoding="utf-8")
    assert section_text(work_text, "一句话结论") == REMNANT
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert section_text(work_text, "方法") == METHOD
    assert section_text(copied_text, "方法") == MAV_METHOD
    assert section_text(copied_text, "表示与架构") == MAV_ARCH
    assert METHOD not in copied_text
    assert REMNANT not in copied_text
    assert section_text(copied_text, "代码与资源") == CODE
    assert section_text(copied_text, "证据状态") == EVIDENCE
    assert section_text(work_text, "代码与资源") == CODE
    assert section_text(copied_text, "研究问题") == MAV_QUESTION
    assert section_text(copied_text, "方法") == MAV_METHOD
    for heading in CLEAR:
        if heading in ("研究问题", "方法", "表示与架构"):
            assert f"## {heading}" in copied_text
            continue
        assert section_text(copied_text, heading) == ""
        assert f"## {heading}" in copied_text
    assert "## 主题" in copied_text
    assert "## 相关论文" in copied_text
    wiki = dest / "wiki" / "video-diffusion.md"
    assert wiki.is_file()
    assert METHOD not in wiki.read_text(encoding="utf-8")
    assert "## 方法" not in wiki.read_text(encoding="utf-8")
    assert MAV_SENTENCE not in (dest / "index.md").read_text(encoding="utf-8")
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_clears_vault_remnants_keeps_work_note(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            MAV,
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    work_text = Path(payload["data"]["note_path"]).read_text(encoding="utf-8")
    copied_text = (dest / "papers" / f"{MAV}.md").read_text(encoding="utf-8")
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert section_text(work_text, "一句话结论") != MAV_SENTENCE
    assert MAV_SENTENCE not in work_text
    assert section_text(copied_text, "研究问题") == MAV_QUESTION
    assert section_text(copied_text, "方法") == MAV_METHOD
    assert section_text(copied_text, "表示与架构") == MAV_ARCH
    for heading in CLEAR:
        if heading in ("研究问题", "方法", "表示与架构"):
            assert f"## {heading}" in copied_text
            continue
        assert section_text(copied_text, heading) == ""
        assert f"## {heading}" in copied_text
    assert section_text(copied_text, "证据状态") == section_text(work_text, "证据状态")
    assert section_text(copied_text, "代码与资源") == section_text(work_text, "代码与资源")
    assert "## 主题" in copied_text
    assert "## 相关论文" in copied_text
    assert "## 主题" not in work_text.split("## 关联", 1)[1]
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []
