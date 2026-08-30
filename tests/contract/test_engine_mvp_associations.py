from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSOCIATIONS = ROOT / "docs" / "seed" / "engine-mvp-associations.json"
LIMITATIONS = ROOT / "docs" / "seed" / "engine-mvp-limitations.json"
EXPERIMENTS = ROOT / "docs" / "seed" / "engine-mvp-experiments.json"
TRAINING = ROOT / "docs" / "seed" / "engine-mvp-training.json"
ARCHITECTURES = ROOT / "docs" / "seed" / "engine-mvp-architectures.json"
METHODS = ROOT / "docs" / "seed" / "engine-mvp-methods.json"
QUESTIONS = ROOT / "docs" / "seed" / "engine-mvp-questions.json"
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "后来成为视频生成论文里最常用的时序评测之一，VBench 等基准会拿它对照。",
    "arxiv-2204.03458": "把图像扩散接到视频上，后面 Make-A-Video、SVD、Latte 都顺着这条线。",
    "arxiv-2209.14792": "证明图像先验可以迁到视频，后面 SVD、DynamiCrafter 也走这条路。",
    "arxiv-2210.02399": "离散 token 加可变时长，和 MAGVIT、VideoPoet 同属 tokenizer 路线。",
    "arxiv-2212.05199": "3D tokenizer 和掩码生成，后面 CogVideoX 一类也用 3D 压缩。",
    "arxiv-2306.02018": "多条件组合生成，和 MotionCtrl、DynamiCrafter 都在做可控运动。",
    "arxiv-2307.06942": "大规模视频-文本数据，和 Panda-70M 一起支撑后面的基础模型。",
    "arxiv-2310.12190": "图生视频动画，接在 SVD 图像先验和 VideoComposer 条件控制之间。",
    "arxiv-2311.15127": "图像扩散改视频的开源基线，后面很多图生视频都从它微调。",
    "arxiv-2311.17982": "细粒度评测，补 FVD 只给一个距离的不足。",
    "arxiv-2312.03641": "把运动拆成相机和物体，接在 VideoComposer 的条件控制上。",
    "arxiv-2312.14125": "语言模型做视频，和 Phenaki 的 token 路线相近，和扩散路线对照。",
    "arxiv-2401.03048": "把 DiT 接到视频扩散，后面 CogVideoX、HunyuanVideo 也用 Transformer。",
    "arxiv-2401.12945": "一次生成整段，对照先抽关键帧再插帧的级联扩散。",
    "arxiv-2402.19479": "自动配字幕的数据，规模上接 InternVid。",
    "arxiv-2405.18750": "蒸馏加速采样，教师一般是已有文生视频扩散。",
    "arxiv-2408.06072": "大规模 DiT 文生视频，架构上接 Latte 和 3D VAE 压缩。",
    "arxiv-2410.05954": "流匹配替代扩散采样，和 DiT 文生视频对照。",
    "arxiv-2412.03603": "开源大规模 DiT，和 CogVideoX 同期对标。",
}
FROZEN_SHA256 = "be2986134292dc55632dd9c755409017f3b3f87a5124564bbe64d69465a46336"
FROZEN_LIMITATIONS_SHA256 = (
    "84836c65c781d6f39ee0c6652b9fd7ba54dff2cb2806b8ec74737c81d9b12e2e"
)
FROZEN_EXPERIMENTS_SHA256 = (
    "8ebc74688def36961b1e4725c881aada4d5d9fc0832014e6e5f5671940be668f"
)
FROZEN_TRAINING_SHA256 = (
    "60ec8a0791285bbabe6cb2c6a1a73e86fb522f635ffbc5f87e4e3e4e03f0dfb4"
)
FROZEN_SEED_SHA256 = (
    "0f8ca52f9d0175837818a8d2fed041280c9ad7691974a75a54b703a4df954717"
)
FROZEN_TOPICS_SHA256 = (
    "3bb9aad76e835b1f77c14bf6f83c7e039997763f78b8b59b22e2682007aedc5b"
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


def test_engine_mvp_associations_file_frozen() -> None:
    assert ASSOCIATIONS.is_file()
    raw = ASSOCIATIONS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["associations"]
    assert payload["associations"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["associations"]) <= seed_ids
    assert len(payload["associations"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
    assert hashlib.sha256(METHODS.read_bytes()).hexdigest() == FROZEN_METHODS_SHA256
    assert hashlib.sha256(ARCHITECTURES.read_bytes()).hexdigest() == FROZEN_ARCHITECTURES_SHA256
    assert hashlib.sha256(TRAINING.read_bytes()).hexdigest() == FROZEN_TRAINING_SHA256
    assert hashlib.sha256(EXPERIMENTS.read_bytes()).hexdigest() == FROZEN_EXPERIMENTS_SHA256
    assert hashlib.sha256(LIMITATIONS.read_bytes()).hexdigest() == FROZEN_LIMITATIONS_SHA256
