from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURES = ROOT / "docs" / "seed" / "engine-mvp-architectures.json"
METHODS = ROOT / "docs" / "seed" / "engine-mvp-methods.json"
QUESTIONS = ROOT / "docs" / "seed" / "engine-mvp-questions.json"
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "用预训练视频网络提取特征，再算真实与生成视频的分布距离。",
    "arxiv-2204.03458": "空间-时间卷积 U-Net，在视频上做扩散。",
    "arxiv-2209.14792": "图像 U-Net 加上伪 3D 时空卷积和时空注意力。",
    "arxiv-2210.02399": "C-ViViT 把时空块压成 token，再交给 transformer。",
    "arxiv-2212.05199": "3D CNN tokenizer，离散视频码本。",
    "arxiv-2306.02018": "时空条件编码器加视频扩散 U-Net。",
    "arxiv-2307.06942": "视频-文本双塔表征，用来做检索和对齐。",
    "arxiv-2310.12190": "把图像条件注入视频扩散 U-Net。",
    "arxiv-2311.15127": "在 Stable Diffusion U-Net 里插入时间卷积和注意力。",
    "arxiv-2311.17982": "评测套件由多个预训练打分模型组成，不训练生成主干。",
    "arxiv-2312.03641": "在视频扩散 U-Net 里加相机和物体运动控制模块。",
    "arxiv-2312.14125": "自回归 Transformer，多模态 token 序列。",
    "arxiv-2401.03048": "潜空间里的纯 Transformer 视频 DiT。",
    "arxiv-2401.12945": "空间-时间 U-Net，一次生成完整时空分辨率。",
    "arxiv-2402.19479": "多教师字幕模型组成的数据管线，不是生成主干。",
    "arxiv-2405.18750": "学生视频扩散网络，由教师模型和奖励模型蒸馏。",
    "arxiv-2408.06072": "3D 因果 VAE 加 DiT 主干。",
    "arxiv-2410.05954": "多尺度金字塔上的流匹配网络。",
    "arxiv-2412.03603": "大规模视频 DiT 加 3D VAE。",
}
FROZEN_SHA256 = "85c4f71517cf84f04850c25e7fe70fa10e771930cf854bea68fc93cc3da9eb73"
FROZEN_SEED_SHA256 = (
    "31ea7461e3cf313a4cd49b651a281e6d7ec8e70b5d98119071bbc4b2d3f79025"
)
FROZEN_TOPICS_SHA256 = (
    "65b4f48decbf840b945723faff757642f515952ac85f03b0f8c430450574b45e"
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


def test_engine_mvp_architectures_file_frozen() -> None:
    assert ARCHITECTURES.is_file()
    raw = ARCHITECTURES.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["architectures"]
    assert payload["architectures"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["architectures"]) <= seed_ids
    assert len(payload["architectures"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
    assert hashlib.sha256(METHODS.read_bytes()).hexdigest() == FROZEN_METHODS_SHA256
