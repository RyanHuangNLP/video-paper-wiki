from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "docs" / "seed" / "engine-mvp-questions.json"
CONCLUSIONS = ROOT / "docs" / "seed" / "engine-mvp-conclusions.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "arxiv-1812.01717": "怎么用分布距离可靠地评测生成视频，而不只看单帧质量？",
    "arxiv-2204.03458": "扩散模型怎样从图像扩展到有时序结构的视频？",
    "arxiv-2209.14792": "没有成对视频-文本数据时，怎样做文生视频？",
    "arxiv-2210.02399": "怎样生成可变时长、叙事连贯的文生视频？",
    "arxiv-2212.05199": "怎样用一个 tokenizer 加生成模型覆盖多种视频合成任务？",
    "arxiv-2306.02018": "怎样把文本、图像、运动等多种条件组合进视频生成？",
    "arxiv-2307.06942": "怎样构建能训练视频基础模型的大规模视频-文本数据？",
    "arxiv-2310.12190": "怎样用视频扩散把静图做成内容一致的动画？",
    "arxiv-2311.15127": "怎样把图像扩散先验改成高质量图生视频？",
    "arxiv-2311.17982": "怎样细粒度评测视频生成，而不只给一个总分？",
    "arxiv-2312.03641": "怎样分别控制生成视频里的相机运动和物体运动？",
    "arxiv-2312.14125": "怎样用自回归语言模型做多模态视频生成？",
    "arxiv-2401.03048": "Transformer 能不能作为视频扩散的主干？",
    "arxiv-2401.12945": "怎样一次生成整段视频，避免先抽帧再插帧的伪影？",
    "arxiv-2402.19479": "怎样自动给海量视频配上高质量字幕？",
    "arxiv-2405.18750": "怎样在少步采样下保持文生视频质量？",
    "arxiv-2408.06072": "怎样用大规模 DiT 生成较长且文本对齐的视频？",
    "arxiv-2410.05954": "怎样用多尺度流匹配更高效地生成视频？",
    "arxiv-2412.03603": "怎样做出可开源的大规模文生视频系统？",
}
FROZEN_SHA256 = "c804de135968662077543ed3e1645f81673087ec5cb102f5be296814bc8c4753"
FROZEN_SEED_SHA256 = (
    "1cbe8451f72f04699b3c7e910d061ec4ce46e14c1b13812701961b165142b315"
)
FROZEN_TOPICS_SHA256 = (
    "7f5c61a14fdf78d0d37f685dd56f12189e006c229b3a8518bd74b74a18502f51"
)
FROZEN_RELATED_SHA256 = (
    "03454c4833c436af191eaa1eb775070609d13371d4d724893112decb95c8f621"
)
FROZEN_CONCLUSIONS_SHA256 = (
    "09bd26c42f224b603fb555b88e056715e282058fe18a700cb623803b963b7e65"
)


def test_engine_mvp_questions_file_frozen() -> None:
    assert QUESTIONS.is_file()
    raw = QUESTIONS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["questions"]
    assert payload["questions"] == EXPECTED
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert set(payload["questions"]) <= seed_ids
    assert len(payload["questions"]) == 19
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
    assert hashlib.sha256(RELATED.read_bytes()).hexdigest() == FROZEN_RELATED_SHA256
    assert hashlib.sha256(CONCLUSIONS.read_bytes()).hexdigest() == FROZEN_CONCLUSIONS_SHA256
