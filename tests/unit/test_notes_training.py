from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes.section import section_text
from video_paper_wiki.notes.training import apply_frozen_training

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

MAV = "arxiv-2209.14792"
MAV_QUESTION = "没有成对视频-文本数据时，怎样做文生视频？"
MAV_SENTENCE = "用图像扩散先验做文生视频，不必成对的视频-文本数据。"
MAV_METHOD = "先训图像扩散，再加时空卷积和注意力，用图像-文本对齐做文生视频。"
MAV_ARCH = "图像 U-Net 加上伪 3D 时空卷积和时空注意力。"
MAV_TRAIN = "先用图像-文本数据训图像扩散，再用无标签视频学时空模块。"
MAV_EXP = "无成对视频-文本数据也能做出有竞争力的文生视频。"
MAV_LIMIT = "没有成对视频-文本，细粒度文本控制偏弱。"
MAV_ASSOC = "证明图像先验可以迁到视频，后面 SVD、DynamiCrafter 也走这条路。"
REMNANT = "This truncated PDF remnant should not stay on the paper copy."
EXPERIMENTS = "The experiment leftover should stay put."
STILL_EMPTY: tuple[str, ...] = ()


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_apply_replaces_only_training_body() -> None:
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
        f"{REMNANT}\n"
        "\n"
        "## 实验与结果\n"
        "\n"
        f"{EXPERIMENTS}\n"
        "\n"
        "## 主题\n"
        "\n"
        "[视频扩散](../wiki/video-diffusion.md)\n"
    )
    yaml = text.split("---", 2)[1]
    out = apply_frozen_training(text, MAV)
    assert section_text(out, "训练与数据") == MAV_TRAIN
    assert REMNANT not in out
    assert section_text(out, "一句话结论") == MAV_SENTENCE
    assert section_text(out, "研究问题") == MAV_QUESTION
    assert section_text(out, "方法") == MAV_METHOD
    assert section_text(out, "表示与架构") == MAV_ARCH
    assert section_text(out, "实验与结果") == EXPERIMENTS
    assert section_text(out, "主题") == "[视频扩散](../wiki/video-diffusion.md)"
    assert out.split("---", 2)[1] == yaml
    assert out.index("## 表示与架构") < out.index("## 训练与数据")
    assert "## 训练与数据\n\n" + MAV_TRAIN + "\n\n## 实验与结果" in out


def test_apply_skips_unknown_paper_and_missing_heading() -> None:
    remnant = (
        "## 训练与数据\n"
        "\n"
        f"{REMNANT}\n"
        "\n"
        "## 实验与结果\n"
        "\n"
        f"{EXPERIMENTS}\n"
    )
    assert apply_frozen_training(remnant, "fixture-unknown") == remnant
    assert apply_frozen_training(remnant, "") == remnant
    no_heading = f"# title\n\n{REMNANT}\n"
    assert apply_frozen_training(no_heading, MAV) == no_heading
    assert "## 训练与数据" not in apply_frozen_training(no_heading, MAV)


def test_review_export_swaps_vault_training_keeps_work_note(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV
    document["title"] = "Make-A-Video"
    document["claims"] = [
        {
            "claim_text": REMNANT,
            "section": "training_data",
            "core": True,
            "assessment": "provisional",
            "locators": [],
        },
        {
            "claim_text": EXPERIMENTS,
            "section": "experiments_results",
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
    assert section_text(work_text, "训练与数据") == REMNANT
    assert section_text(copied_text, "训练与数据") == MAV_TRAIN
    assert section_text(copied_text, "实验与结果") == MAV_EXP
    assert section_text(copied_text, "局限") == MAV_LIMIT
    assert section_text(copied_text, "关联") == MAV_ASSOC
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert section_text(copied_text, "研究问题") == MAV_QUESTION
    assert section_text(copied_text, "方法") == MAV_METHOD
    assert section_text(copied_text, "表示与架构") == MAV_ARCH
    assert REMNANT not in copied_text
    assert MAV_TRAIN not in work_text
    assert section_text(work_text, "实验与结果") == EXPERIMENTS
    for heading in STILL_EMPTY:
        assert section_text(copied_text, heading) == ""
        assert f"## {heading}" in copied_text
    assert section_text(copied_text, "代码与资源") == section_text(work_text, "代码与资源")
    assert section_text(copied_text, "证据状态") == "provisional"
    assert "local pypdf extract" not in section_text(copied_text, "证据状态")
    assert "## 主题" in copied_text
    assert "## 相关论文" in copied_text
    wiki_text = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert MAV_TRAIN not in wiki_text
    assert "## 训练与数据" not in wiki_text
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert MAV_TRAIN not in index_text
    assert "## 训练与数据" not in index_text
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_writes_frozen_training_on_vault_copy(
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
    assert section_text(copied_text, "训练与数据") == MAV_TRAIN
    assert section_text(copied_text, "实验与结果") == MAV_EXP
    assert section_text(copied_text, "局限") == MAV_LIMIT
    assert section_text(copied_text, "关联") == MAV_ASSOC
    assert section_text(copied_text, "表示与架构") == MAV_ARCH
    assert section_text(copied_text, "方法") == MAV_METHOD
    assert section_text(copied_text, "研究问题") == MAV_QUESTION
    assert section_text(copied_text, "一句话结论") == MAV_SENTENCE
    assert MAV_TRAIN not in work_text
    assert MAV_ARCH not in work_text
    assert MAV_METHOD not in work_text
    assert MAV_QUESTION not in work_text
    assert MAV_SENTENCE not in work_text
    for heading in STILL_EMPTY:
        assert section_text(copied_text, heading) == ""
    assert "## 主题" in copied_text
    assert "## 相关论文" in copied_text
    wiki_text = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert MAV_TRAIN not in wiki_text
    assert "## 训练与数据" not in wiki_text
    assert MAV_TRAIN not in (dest / "index.md").read_text(encoding="utf-8")
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []
