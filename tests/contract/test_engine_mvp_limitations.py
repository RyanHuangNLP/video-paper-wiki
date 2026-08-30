from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    "arxiv-1812.01717": "依赖预训练特征空间，对分布外视频不一定可靠。",
    "arxiv-2204.03458": "早期视频扩散计算贵，时长和分辨率都有限。",
    "arxiv-2209.14792": "没有成对视频-文本，细粒度文本控制偏弱。",
    "arxiv-2210.02399": "长视频容易积累误差，离散 token 会损失细节。",
    "arxiv-2212.05199": "离散码本容量和压缩率要折中，开放域文生视频不是重点。",
    "arxiv-2306.02018": "多种条件要对齐，条件缺失或冲突时不稳定。",
    "arxiv-2307.06942": "网络视频噪声大，自动对齐的文本质量不均。",
    "arxiv-2310.12190": "运动幅度和时长有限，难做大范围镜头运动。",
    "arxiv-2311.15127": "主要是图生视频，文本控制和长视频仍弱。",
    "arxiv-2311.17982": "自动打分模型和人类判断仍有差距，维度也不完备。",
    "arxiv-2312.03641": "依赖运动标注或估计，复杂多物体交互仍难。",
    "arxiv-2312.14125": "自回归采样慢，长程一致性和开源复现都受限。",
    "arxiv-2401.03048": "规模小于同期商业系统，长视频和精细控制一般。",
    "arxiv-2401.12945": "一次生成整段对显存要求高，分辨率和时长仍受限。",
    "arxiv-2402.19479": "自动字幕会错，片段切分也可能切断语义。",
    "arxiv-2405.18750": "蒸馏依赖教师和奖励模型，可能放大它们的偏差。",
    "arxiv-2408.06072": "长叙事和复杂运动仍不稳，算力门槛高。",
    "arxiv-2410.05954": "多尺度会累积误差，文本对齐未必强于专用文生视频。",
    "arxiv-2412.03603": "训练和推理成本高，安全和版权风险仍在。",
}
FROZEN_SHA256 = "84836c65c781d6f39ee0c6652b9fd7ba54dff2cb2806b8ec74737c81d9b12e2e"
FROZEN_EXPERIMENTS_SHA256 = (
    "8ebc74688def36961b1e4725c881aada4d5d9fc0832014e6e5f5671940be668f"
)
FROZEN_TRAINING_SHA256 = (
    "60ec8a0791285bbabe6cb2c6a1a73e86fb522f635ffbc5f87e4e3e4e03f0dfb4"
)
FROZEN_SEED_SHA256 = (
    "dae496b5b077e1945b5ac13a7248225ca2e73a475502bbe810dedabe3068028a"
)
FROZEN_TOPICS_SHA256 = (
    "0220e6aa3d0c98844985ff701d330e1c2907ba9135eb713ca7c8274fb786be1e"
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


def test_engine_mvp_limitations_file_frozen() -> None:
    assert LIMITATIONS.is_file()
    raw = LIMITATIONS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["limitations"]
    assert payload["limitations"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["limitations"]) <= seed_ids
    assert len(payload["limitations"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
    assert hashlib.sha256(METHODS.read_bytes()).hexdigest() == FROZEN_METHODS_SHA256
    assert hashlib.sha256(ARCHITECTURES.read_bytes()).hexdigest() == FROZEN_ARCHITECTURES_SHA256
    assert hashlib.sha256(TRAINING.read_bytes()).hexdigest() == FROZEN_TRAINING_SHA256
    assert hashlib.sha256(EXPERIMENTS.read_bytes()).hexdigest() == FROZEN_EXPERIMENTS_SHA256
