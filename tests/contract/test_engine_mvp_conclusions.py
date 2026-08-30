from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "提出 Fréchet Video Distance，用特征分布距离评测生成视频。",
    "arxiv-2204.03458": "把扩散模型从图像扩展到视频，用空间-时间 U-Net 做视频生成。",
    "arxiv-2209.14792": "用图像扩散先验做文生视频，不必成对的视频-文本数据。",
    "arxiv-2210.02399": "把视频压成 token，再用 transformer 生成可变时长的文生视频。",
    "arxiv-2212.05199": "3D tokenizer 加掩码生成，把多种视频合成任务放到一个模型里。",
    "arxiv-2306.02018": "把文本、图像、运动等多种条件组合起来控制视频生成。",
    "arxiv-2307.06942": "大规模视频-文本数据集，用来训练视频基础模型。",
    "arxiv-2310.12190": "用视频扩散把静图做成动画，做图生视频。",
    "arxiv-2311.15127": "把 Stable Diffusion 的图像先验改成视频扩散，做图生视频。",
    "arxiv-2311.17982": "细粒度视频生成评测基准，拆成多个质量和对齐维度。",
    "arxiv-2312.03641": "分别控制相机运动和物体运动的视频生成。",
    "arxiv-2312.14125": "用自回归语言模型在多模态 token 上做视频生成。",
    "arxiv-2401.03048": "用纯 Transformer 做视频扩散主干。",
    "arxiv-2401.12945": "空间-时间 U-Net 一次生成整段视频，而不是先抽帧再插帧。",
    "arxiv-2402.19479": "自动配字幕的约 7000 万视频-文本对数据集。",
    "arxiv-2405.18750": "用奖励蒸馏加快文生视频扩散的采样。",
    "arxiv-2408.06072": "大规模 DiT 文生视频模型，能生成约 10 秒的连贯视频。",
    "arxiv-2410.05954": "金字塔式流匹配，在多尺度上生成视频。",
    "arxiv-2412.03603": "开源的大规模文生视频 DiT 系统。",
}
FROZEN_SHA256 = "09bd26c42f224b603fb555b88e056715e282058fe18a700cb623803b963b7e65"
FROZEN_SEED_SHA256 = (
    "395656a16fd5760a2e1064b9688d677997ed776018cc0d80a3a640c5a9f4c8e3"
)
FROZEN_TOPICS_SHA256 = (
    "8e236a37866230927eede4f74c8cc9ebb320fe043f99705ab9c5a44d21341656"
)
FROZEN_RELATED_SHA256 = (
    "03454c4833c436af191eaa1eb775070609d13371d4d724893112decb95c8f621"
)


def test_engine_mvp_conclusions_file_frozen() -> None:
    assert CONCLUSIONS.is_file()
    raw = CONCLUSIONS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["conclusions"]
    assert payload["conclusions"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["conclusions"]) <= seed_ids
    assert len(payload["conclusions"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
