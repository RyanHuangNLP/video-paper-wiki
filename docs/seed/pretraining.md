# 预训练

这 12 篇论文由用户于 2026-09-08 指定为「预训练」类目的种子 paper。类目标识为 `pretraining`；下表中的模型与方法类型仅用于阅读组织，全部论文属于同一个类目。

| 模型 / 方法 | 类型 | 完整论文标题 |
| --- | --- | --- |
| HunyuanVideo 1.0 | 模型 | [HunyuanVideo: A Systematic Framework For Large Video Generative Models](https://arxiv.org/abs/2412.03603) |
| HunyuanVideo 1.5 | 模型 | [HunyuanVideo 1.5 Technical Report](https://arxiv.org/abs/2511.18870) |
| Wan 2.1 | 模型 | [Wan: Open and Advanced Large-Scale Video Generative Models](https://arxiv.org/abs/2503.20314) |
| LongCat-Video | 模型 | [LongCat-Video Technical Report](https://arxiv.org/abs/2510.22200) |
| Waver 1.0 | 模型 | [Waver: Wave Your Way to Lifelike Video Generation](https://arxiv.org/abs/2508.15761) |
| Cosmos 3 | 模型 | [Cosmos 3: Omnimodal World Models for Physical AI](https://arxiv.org/abs/2606.02800) |
| LTX-Video | 模型 | [LTX-Video: Realtime Video Latent Diffusion](https://arxiv.org/abs/2501.00103) |
| LTX-2 | 模型 | [LTX-2: Efficient Joint Audio-Visual Foundation Model](https://arxiv.org/abs/2601.03233) |
| SANA-Video 2.0 | 模型 | [SANA-Video 2.0: Hybrid Linear Attention with Attention Residuals for Efficient Video Generation](https://arxiv.org/abs/2607.21553) |
| SD3 | 方法 | [Scaling Rectified Flow Transformers for High-Resolution Image Synthesis](https://arxiv.org/abs/2403.03206) |
| TQD | 方法 | [Beyond the Golden Data: Resolving the Motion-Vision Quality Dilemma via Timestep Selective Training](https://arxiv.org/abs/2603.25527) |
| Self-Flow | 方法 | [Self-Supervised Flow Matching for Scalable Multi-Modal Synthesis](https://arxiv.org/abs/2603.06507) |

用户指定的方法阅读重点：

- **SD3**：Rectified Flow、timestep sampling 与 shift。
- **TQD**：按视频质量与运动特征选择 timestep。
- **Self-Flow**：Dual-Timestep 与自监督表征学习。

机器可读的[论文清单](pretraining.json)保存完整标题、arXiv ID、稳定 paper ID 和不含追踪参数的链接；[类目映射](pretraining-topics.json)将全部 12 篇论文列为「预训练」种子。论文 ID 沿用 `arxiv-<id>`，其中 HunyuanVideo 与旧种子集共用 `arxiv-2412.03603`。

本清单记录用户选种与元数据分类。2026-09-08 已逐一打开对应 arXiv 摘要页核对标题；尚未下载、摄取论文正文或生成知识记录。它是独立的用户类目种子清单，现有 `vpwiki seed` 命令仍使用固定 67 篇的 `engine-mvp` 集合，不会自动加载本清单。
