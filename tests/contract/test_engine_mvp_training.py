from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / "docs" / "seed" / "engine-mvp-training.json"
ARCHITECTURES = ROOT / "docs" / "seed" / "engine-mvp-architectures.json"
METHODS = ROOT / "docs" / "seed" / "engine-mvp-methods.json"
QUESTIONS = ROOT / "docs" / "seed" / "engine-mvp-questions.json"
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "不训练生成模型，在视频特征空间上比较分布。",
    "arxiv-2204.03458": "在视频片段上做扩散训练，可用像素或潜空间。",
    "arxiv-2209.14792": "先用图像-文本数据训图像扩散，再用无标签视频学时空模块。",
    "arxiv-2210.02399": "用视频-文本对训练 tokenizer 和生成 transformer。",
    "arxiv-2212.05199": "在视频数据上训 3D tokenizer 和掩码生成器。",
    "arxiv-2306.02018": "用带多种条件标注的视频训练组合扩散。",
    "arxiv-2307.06942": "大规模网络视频-文本对，用来训视频基础模型。",
    "arxiv-2310.12190": "用图像-视频对训练图生视频扩散。",
    "arxiv-2311.15127": "在大量视频上把图像扩散先验微调成图生视频。",
    "arxiv-2311.17982": "评测基准自带提示和维度，不依赖某一训练集。",
    "arxiv-2312.03641": "用带相机或物体运动标注的视频训练控制模块。",
    "arxiv-2312.14125": "多模态 token 混合数据上训自回归语言模型。",
    "arxiv-2401.03048": "在视频潜空间上训 DiT。",
    "arxiv-2401.12945": "在视频数据上端到端训空间-时间 U-Net。",
    "arxiv-2402.19479": "自动配字幕建成约 7000 万视频-文本对。",
    "arxiv-2405.18750": "用教师视频模型和奖励模型蒸馏学生网络。",
    "arxiv-2408.06072": "大规模文本-视频数据，图像和视频混合、多分辨率训练。",
    "arxiv-2410.05954": "多尺度上做流匹配训练。",
    "arxiv-2412.03603": "大规模文本-视频数据训练。",
}
FROZEN_SHA256 = "60ec8a0791285bbabe6cb2c6a1a73e86fb522f635ffbc5f87e4e3e4e03f0dfb4"
FROZEN_SEED_SHA256 = (
    "2f0b65e9ce4e57864cadc5367afc0c41999e4c82b1694ee94f440cedd22d7ef6"
)
FROZEN_TOPICS_SHA256 = (
    "a1aa08a996381da317ebed53d6a6860537729d28f371158961676f23086a2b82"
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
FROZEN_METHODS_SHA256 = (
    "ac7e3578d8931d10b3587b042238d1d88a49de8d5f4588ed08fcd7afde935924"
)
FROZEN_ARCHITECTURES_SHA256 = (
    "85c4f71517cf84f04850c25e7fe70fa10e771930cf854bea68fc93cc3da9eb73"
)


def test_engine_mvp_training_file_frozen() -> None:
    assert TRAINING.is_file()
    raw = TRAINING.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["training"]
    assert payload["training"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["training"]) == seed_ids
    assert len(payload["training"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
    assert hashlib.sha256(METHODS.read_bytes()).hexdigest() == FROZEN_METHODS_SHA256
    assert hashlib.sha256(ARCHITECTURES.read_bytes()).hexdigest() == FROZEN_ARCHITECTURES_SHA256
