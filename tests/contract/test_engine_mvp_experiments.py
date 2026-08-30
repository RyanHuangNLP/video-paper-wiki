from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    "arxiv-1812.01717": "在生成视频上，FVD 比只看单帧的 FID 更能反映时序质量。",
    "arxiv-2204.03458": "在视频生成任务上展示了扩散模型可以产生连贯视频。",
    "arxiv-2209.14792": "无成对视频-文本数据也能做出有竞争力的文生视频。",
    "arxiv-2210.02399": "能生成可变时长、开放域的文生视频。",
    "arxiv-2212.05199": "在多个视频合成基准上，一个模型覆盖多种任务。",
    "arxiv-2306.02018": "多种条件可以组合控制生成视频的内容和运动。",
    "arxiv-2307.06942": "用该数据训练的视频-语言模型在表征和检索上提升。",
    "arxiv-2310.12190": "图生视频能保持图像内容并补上合理运动。",
    "arxiv-2311.15127": "图像先验微调后的图生视频，明显好于从零训视频扩散。",
    "arxiv-2311.17982": "细粒度维度能分开质量、运动、对齐等问题，而不是一个总分。",
    "arxiv-2312.03641": "相机轨迹和物体运动可以分别按给定信号控制。",
    "arxiv-2312.14125": "自回归语言模型可以做多种视频生成和编辑任务。",
    "arxiv-2401.03048": "纯 Transformer 视频扩散在常用基准上达到当时可比水平。",
    "arxiv-2401.12945": "一次生成整段视频，减少级联抽帧插帧的伪影。",
    "arxiv-2402.19479": "用该数据训练的模型在视频-文本任务上优于较小数据。",
    "arxiv-2405.18750": "少步采样下仍接近教师模型的文生视频质量。",
    "arxiv-2408.06072": "能生成约 10 秒、文本对齐较好的视频，并开源权重。",
    "arxiv-2410.05954": "多尺度流匹配在效率和质量之间取得折中。",
    "arxiv-2412.03603": "开源大规模文生视频，可与同期系统比较。",
}
FROZEN_SHA256 = "8ebc74688def36961b1e4725c881aada4d5d9fc0832014e6e5f5671940be668f"
FROZEN_TRAINING_SHA256 = (
    "60ec8a0791285bbabe6cb2c6a1a73e86fb522f635ffbc5f87e4e3e4e03f0dfb4"
)
FROZEN_SEED_SHA256 = (
    "54f07f4b9b813e569d1fccb75178c9f7565afd0a8730189a124d9e5db5013cf5"
)
FROZEN_TOPICS_SHA256 = (
    "676859e7a449ac251f5c18986b408f7f067ad549133a76276f8a38f9eccac8b8"
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


def test_engine_mvp_experiments_file_frozen() -> None:
    assert EXPERIMENTS.is_file()
    raw = EXPERIMENTS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["experiments"]
    assert payload["experiments"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["experiments"]) <= seed_ids
    assert len(payload["experiments"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
    assert hashlib.sha256(QUESTIONS.read_bytes()).hexdigest() == FROZEN_QUESTIONS_SHA256
    assert hashlib.sha256(METHODS.read_bytes()).hexdigest() == FROZEN_METHODS_SHA256
    assert hashlib.sha256(ARCHITECTURES.read_bytes()).hexdigest() == FROZEN_ARCHITECTURES_SHA256
    assert hashlib.sha256(TRAINING.read_bytes()).hexdigest() == FROZEN_TRAINING_SHA256
