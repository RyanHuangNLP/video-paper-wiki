# 真实 PDF 问答 / 写作验收草案

**状态：待核对的验收草案。不是人工确认的标准答案。不宣称通过率，不关闭人工 gate。**

本文仅根据用户已放入仓库 `inbox/` 的本地 PDF、用默认环境 `pypdf` 抽出的文字整理，供集成完成后实际跑检索问答与简单写作时对照。未操作真实 Vault，未运行 `vpwiki-admin`，未安装或下载 Docling/生成模型。

## 选用论文

| 项 | 记录 |
| --- | --- |
| 相对路径 | `inbox/arxiv-2311.15127.pdf` |
| 绝对路径 | `/Users/huangzhanpeng/python_code/video-paper-wiki/inbox/arxiv-2311.15127.pdf` |
| SHA-256 | `654ef597e183c0544cd753494cb442125bc42b17dd2477481b6799114482a92e` |
| 页数 | 30（pypdf；30 页均有非空文字） |
| 元数据标题 | 缺省（PDF Info 无 title） |
| 正文标题（第 1 页抽出） | Stable Video Diffusion: Scaling Latent Video Diffusion Models to Large Datasets |
| 页 1 行内标识 | arXiv:2311.15127v1 [cs.CV] 25 Nov 2023 |

inbox 中另有 `arxiv-2204.03458.pdf`（Video Diffusion Models，15 页可抽字）和 `arxiv-2311.17982.pdf`（VBench，28 页可抽字）。本草案只选一篇：SVD 同时给出训练阶段、数据规模和可核对数字。

## 五个可从论文回答的问题

### Q1. SVD 是什么，面向哪些生成任务？

- **页码：** 1
- **证据摘录：** `We present Stable Video Diffusion — a latent video diffu-`
- **同页续：** `and image-to-video generation.`
- **预期回答要点：** SVD 是 latent video diffusion model；论文将其用于高分辨率 text-to-video 与 image-to-video。不要写进本页没有的产品名。

### Q2. 作者给出的三阶段训练是什么？

- **页码：** 3
- **证据摘录：** `Stage I: image pretraining`
- **同页：** Stage II video pretraining；Stage III video finetuning on a smaller high-quality subset。
- **预期回答要点：** Stage I 图像预训练；Stage II 大规模视频预训练；Stage III 高质量、更高分辨率微调。

### Q3. 如何把预训练图像 LDM 改成视频模型？

- **页码：** 3
- **证据摘录：** `insert temporal convolution and attention layers after every`
- **同页：** `we finetune the full model.`
- **预期回答要点：** 在每个 spatial convolution/attention 之后插入 temporal convolution 与 attention；与只训时间层或 training-free 方法不同，本文微调全模型。

### Q4. 初始 LVD 有多大规模，用什么信号过滤？

- **页码：** 4
- **证据摘录：** `Dataset (LVD), consists of 580M annotated video clip pairs,`
- **同页：** `forming 212 years of content.`；optical flow 去掉近静态镜头；OCR 去掉大量文字。
- **预期回答要点：** 正文写 580M 标注 clip pairs、212 years；同页 Table 1 列出过滤前 577M clips。过滤信号包括光流幅度、OCR、CLIP 美学/图文相似度。不要编造阈值数字（页上写的是 “a certain threshold”）。

### Q5. UCF-101 FVD 以及 25 帧 I2V 相对 GEN-2 / PikaLabs 的人类偏好？

- **页码：** 6
- **证据摘录：** `SVD (ours) 242.02`
- **同页：** `Our 25 frame Image-` / `human voters over GEN-2 [74]`
- **预期回答要点：** Table 2 报 SVD FVD 242.02；Figure 6 称 25-frame image-to-video 被人类投票者偏好于 GEN-2 与 PikaLabs。不要把偏好图改写成页上没有印出的胜率百分比。

## 两个论文不能充分回答的问题

### U1. 25 帧 576×1024 I2V 在 RTX 4090 上的实测时延和峰值显存？

- **应表达的证据不足：** 第 15 页只定性写了 “slow to sample and have high VRAM requirements, and our model is no exception”，没有该卡、该分辨率的秒数或 GB。应拒绝编造测量值，最多复述定性局限。

### U2. SVD 与 OpenAI Sora 或 Kling 在同一人类偏好协议上的数字对比？

- **应表达的证据不足：** 抽出文本未出现 Sora 或 Kling。闭源对比仅有 GEN-2 与 PikaLabs。不能把页 6–7 的偏好推广到未出现的模型。

## 简单写作任务

| 项 | 要求 |
| --- | --- |
| 主题 | Stable Video Diffusion 如何用三阶段训练和数据策展支撑 text-to-video 与 image-to-video |
| 读者 | 视频生成研究 wiki 的初读者（要能对页核对，不要求复现训练） |
| 篇幅 | 约 600–900 汉字的可编辑短稿 |
| 结构 | 一句话结论 → 方法（骨干/时间层/全模型微调）→ 数据与三阶段 → 报告结果 → 局限 |
| 引用要求 | 只引用本 PDF 已抽出的页码与摘录；数字必须能在对应页找到；禁止未出现的模型名、硬件基准或通过率；输出可编辑 Markdown 和绑定这些证据的基本参考文献，而不是 paper-analysis-draft JSON |

## 边界

- 不是 HUMAN-* gate 的关闭证据。
- 不是检索/问答评测的 gold 或通过率。
- 集成后应用本草案做实际运行核对，而不是把本文件本身当成已验收。
