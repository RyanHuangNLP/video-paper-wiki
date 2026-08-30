from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METHODS = ROOT / "docs" / "seed" / "engine-mvp-methods.json"
QUESTIONS = ROOT / "docs" / "seed" / "engine-mvp-questions.json"
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "用预训练视频特征的分布距离比较真实视频和生成视频。",
    "arxiv-2204.03458": "在空间-时间 U-Net 上做视频扩散，对整段视频加噪去噪。",
    "arxiv-2209.14792": "先训图像扩散，再加时空卷积和注意力，用图像-文本对齐做文生视频。",
    "arxiv-2210.02399": "用 tokenizer 把视频压成 token，再用 transformer 生成可变长视频。",
    "arxiv-2212.05199": "3D tokenizer 把视频编成离散码，再用掩码生成做多种合成任务。",
    "arxiv-2306.02018": "用编码器把文本、图像、运动等多种条件送进视频扩散。",
    "arxiv-2307.06942": "从网络视频收集并清洗大规模视频-文本对，训练视频-语言表征。",
    "arxiv-2310.12190": "把图像条件注入视频扩散，给静图补运动。",
    "arxiv-2311.15127": "在图像扩散先验上插入时间层，做图生视频微调。",
    "arxiv-2311.17982": "把视频生成质量拆成多个可自动打分的维度和提示套件。",
    "arxiv-2312.03641": "分别注入相机轨迹和物体运动信号，控制生成视频里的运动。",
    "arxiv-2312.14125": "把图像、视频、文本编成 token，用自回归语言模型生成。",
    "arxiv-2401.03048": "把视频当成时空 token，用 Transformer 做潜空间视频扩散。",
    "arxiv-2401.12945": "空间-时间 U-Net 在完整时空分辨率上一次采样整段视频。",
    "arxiv-2402.19479": "用多个模型给视频片段自动配字幕，建成约 7000 万对数据。",
    "arxiv-2405.18750": "用奖励蒸馏教师文生视频模型，减少采样步数。",
    "arxiv-2408.06072": "3D 因果 VAE 加 DiT 主干，用大规模文本-视频数据训练。",
    "arxiv-2410.05954": "金字塔式流匹配，从低分辨率到高分辨率生成视频。",
    "arxiv-2412.03603": "在大规模数据上训练 DiT 文生视频系统，并开源权重。",
}
FROZEN_SHA256 = "ac7e3578d8931d10b3587b042238d1d88a49de8d5f4588ed08fcd7afde935924"
FROZEN_SEED_SHA256 = (
    "1403babb260be775ed80505562ca39bab7d9d13fba4d9e1cae3fb5409285483d"
)
FROZEN_TOPICS_SHA256 = (
    "789a1c94e86bb9a4ecc70ce06f27348591749db792a267761f1df12edae6af33"
)
FROZEN_RELATED_SHA256 = (
    "03454c4833c436af191eaa1eb775070609d13371d4d724893112decb95c8f621"
)
FROZEN_CONCLUSIONS_SHA256 = (
    "09bd26c42f224b603fb555b88e056715e282058fe18a700cb623803b963b7e65"
)
FROZEN_QUESTIONS_SHA256 = (
    "c804de135968662077543ed3e1645f81673087ec5cb102f5be296814bc8c4753"
)


def test_engine_mvp_methods_file_frozen() -> None:
    assert METHODS.is_file()
    raw = METHODS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["methods"]
    assert payload["methods"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["methods"]) <= seed_ids
    assert len(payload["methods"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
