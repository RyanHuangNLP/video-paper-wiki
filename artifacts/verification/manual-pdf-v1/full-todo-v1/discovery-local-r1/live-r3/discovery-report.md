# Discovery svd\-holdout\-r2

State: calculated\_stopped

All scientific coverage and relevance remain provisional.

How do staged training and data curation affect video diffusion model quality and downstream transfer?

## Progress

Stop reasons: \[&quot;budget\_exhausted&quot;\]

Budget used: \{&quot;candidate\_slots\_reserved&quot;:1,&quot;current\_candidate\_components&quot;:1,&quot;normalized\_payload\_bytes&quot;:3053,&quot;observation\_slots\_reserved&quot;:2,&quot;pending\_observations&quot;:0,&quot;pending\_request\_files&quot;:0,&quot;request\_slots\_reserved&quot;:2,&quot;requests\_materialized&quot;:2,&quot;result\_records&quot;:5,&quot;retry\_slots&quot;:0,&quot;rounds\_completed&quot;:1,&quot;rounds\_planned&quot;:1,&quot;terminal\_observations&quot;:2\}

Budget remaining: \{&quot;candidate\_slots&quot;:31,&quot;observations&quot;:0,&quot;payload\_bytes&quot;:2094099,&quot;requests&quot;:0,&quot;results&quot;:5,&quot;rounds&quot;:0\}

## Completed provisional coverage

Round 1: \{&quot;id&quot;:&quot;rw3:research\-assessment:b5fd7e6215a0dda42418887e50d5e65063448f4fd5bcf1d87b37fc127e234170&quot;,&quot;sha256&quot;:&quot;d799b2eb9b7b6e8154ee59ee49ccabbccadd803cd2c3d17e834d77bc1f04a1ee&quot;\}

Generator: \{&quot;identity\_source&quot;:&quot;self\_reported&quot;,&quot;reason&quot;:null,&quot;value&quot;:&quot;gpt\-6\-astra&quot;\}

- method: gap

  Scope: training stages, objectives, and data selection

  已观察到训练阶段的简短描述，仍不足以比较各阶段及数据筛选对质量和迁移的影响。

  Reason: 缺少训练目标、数据筛选条件、对照实验和效应量。

  Evidence: \[\{&quot;end&quot;:80,&quot;excerpt\_sha256&quot;:&quot;54565a98ba18813d29d53c39649d822fbfb36ced010f3ae5b42e7723b260ce4e&quot;,&quot;field&quot;:&quot;summary&quot;,&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:2,&quot;start&quot;:0\}\]

- benchmark: gap

  Scope: datasets, evaluation protocol, metrics, and comparisons

  当前保存的摘要片段没有可核验的评测条件或数值结果。

  Reason: 缺少数据集划分、指标定义、样本规模和可比较的基线结果。

- implementation: gap

  Scope: pipeline details, conditioning, adaptation, and compute

  当前证据不足以重建实现和适配过程。

  Reason: 尚未观察到具体管线、条件输入、适配设置或计算资源。

- counterevidence: gap

  Scope: limitations, ablations, failures, and contrary evidence

  当前证据不能说明反例、失败条件和实验局限。

  Reason: 没有保留消融、负面结果或与其他研究冲突的证据。

- reproduction: gap

  Scope: code, data, hyperparameters, and reproducibility details

  当前证据不足以提出可执行的复现方案。

  Reason: 没有精确代码版本、配置、数据清单、超参数或运行条件。

## Operation health

- Round 1, slot 0: platform\-web\-search\-normalized\-v1 / lookup / method: success

  Request: \{&quot;id&quot;:&quot;rw3:discovery\-request:4be2cb117a8d5c2a89c1116ed73dff7b5b2d80cd15e76f22a8ecb4e77806f1e2&quot;,&quot;sha256&quot;:&quot;060f96ae2a62766721d6b2366fc52236b026ce6a5009697159b819179d6df2a4&quot;\}; observation: \{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\}

- Round 1, slot 1: openalex\-rest\-normalized\-v1 / topic / method: capability\_unavailable

  Request: \{&quot;id&quot;:&quot;rw3:discovery\-request:4b302babe2e3849c99e2ae7d97b93285c5ca41a1bba74bf05bd1116ac0182fea&quot;,&quot;sha256&quot;:&quot;5f60e1aa6a405820684da97f9a4120d0cbb771a1be229ed42fbf5804167610f5&quot;\}; observation: \{&quot;id&quot;:&quot;rw3:discovery\-observation:2e62bbd9804d966a8e6abf524cba0c0f727aa0bd9295d3220512bad9b4a5a4dc&quot;,&quot;sha256&quot;:&quot;cef87f73a879ccbf81afd7d0aac3bd4a632244bc2a624dfd4591ce368c33c2da&quot;\}

  Failure: \{&quot;code&quot;:&quot;HOST\_SAFE\_OPEN\_UNAVAILABLE&quot;,&quot;message&quot;:&quot;The host returned: is not safe to open \(non\-retryable error\)\. No OpenAlex payload was visible\.&quot;,&quot;retry\_after\_seconds&quot;:null\}


## Candidates from completed round 1

Showing 1 of 1 candidates; 0 omitted from this preview.

Complete candidate evidence: \{&quot;path&quot;:&quot;/Users/huangzhanpeng/python\_code/video\-paper\-wiki/\.work/parallel/discovery\-expansion\-v1/terminal\-1/source/\.work/research/svd\-holdout\-r2/discovery\-v1/proposals/6178d275b957a89ec3efe6ee94f04010bbeeb828379fbc918d953ef3f3d65914\.json&quot;,&quot;reference&quot;:\{&quot;id&quot;:&quot;rw3:paper\-candidate\-set:6178d275b957a89ec3efe6ee94f04010bbeeb828379fbc918d953ef3f3d65914&quot;,&quot;sha256&quot;:&quot;d8d803529bbd1225aec58ca5795cfa5bd7f6bc15af019968cc7900456ce4ec22&quot;\}\}

Complete ranking evidence: \{&quot;path&quot;:&quot;/Users/huangzhanpeng/python\_code/video\-paper\-wiki/\.work/parallel/discovery\-expansion\-v1/terminal\-1/source/\.work/research/svd\-holdout\-r2/discovery\-v1/proposals/ba0d9092f45c4907ad5ba0d00b19a25c5fa3594455494ec97c9ec39f817857a6\.json&quot;,&quot;reference&quot;:\{&quot;id&quot;:&quot;rw3:paper\-rank:ba0d9092f45c4907ad5ba0d00b19a25c5fa3594455494ec97c9ec39f817857a6&quot;,&quot;sha256&quot;:&quot;6ef3d732959f0f73cdf2078ebb020a170e69c005711c05f25f309cdea37eea19&quot;\}\}

### Stable Video Diffusion: Scaling Latent Video Diffusion Models to Large Datasets

Candidate key: 72fb3b8aae0c36ab732a08494117b8dfea1ac1c2f54842505a3bbd5c8afcb726

Identifiers: \[\{&quot;namespace&quot;:&quot;arxiv&quot;,&quot;value&quot;:&quot;2311\.15127&quot;\}\]

Observed versions: \[\{&quot;namespace&quot;:&quot;arxiv&quot;,&quot;value&quot;:&quot;2311\.15127&quot;,&quot;version&quot;:1\}\]

Provisional relevance: \{&quot;assessment&quot;:&quot;provisional\_scientific\_assessment&quot;,&quot;matched\_terms&quot;:\[&quot;finetuning&quot;,&quot;pretraining&quot;,&quot;training&quot;,&quot;video diffusion&quot;\],&quot;relevant&quot;:true\}

Ranking signals: \{&quot;latest\_published\_at&quot;:&quot;2023\-11\-25&quot;,&quot;max\_cited\_by\_count&quot;:null,&quot;min\_depth&quot;:0\}

Rank 1; exact RRF 1/61; scaled score 16393

Suppression reason counts: \{&quot;same\_list\_candidate&quot;:4\}

Contributions (first 1 of 1; 0 omitted): \[\{&quot;class\_key&quot;:&quot;8a237fc83c298cbfefda3bbb7aa384f26a017443caeaeb1deae09e6c995c8da3&quot;,&quot;fact&quot;:\{&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:3\},&quot;list\_key&quot;:\{&quot;lens&quot;:&quot;method&quot;,&quot;operation&quot;:&quot;lookup&quot;,&quot;provider&quot;:&quot;platform\-web\-search\-normalized\-v1&quot;,&quot;seed\_key&quot;:&quot;svd&quot;\},&quot;rank&quot;:1,&quot;reason&quot;:null\}\]

Suppressed (first 3 of 4; 1 omitted): \[\{&quot;class\_key&quot;:&quot;b763366546e6db459227117d93a4ba2c12f9aed3be627b411f04dcfe305ed154&quot;,&quot;fact&quot;:\{&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:5\},&quot;list\_key&quot;:\{&quot;lens&quot;:&quot;method&quot;,&quot;operation&quot;:&quot;lookup&quot;,&quot;provider&quot;:&quot;platform\-web\-search\-normalized\-v1&quot;,&quot;seed\_key&quot;:&quot;svd&quot;\},&quot;rank&quot;:1,&quot;reason&quot;:&quot;same\_list\_candidate&quot;\},\{&quot;class\_key&quot;:&quot;ba7eed8489302bbdbdb3733482939793076992024173f655f153d51ff5ff2390&quot;,&quot;fact&quot;:\{&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:1\},&quot;list\_key&quot;:\{&quot;lens&quot;:&quot;method&quot;,&quot;operation&quot;:&quot;lookup&quot;,&quot;provider&quot;:&quot;platform\-web\-search\-normalized\-v1&quot;,&quot;seed\_key&quot;:&quot;svd&quot;\},&quot;rank&quot;:1,&quot;reason&quot;:&quot;same\_list\_candidate&quot;\},\{&quot;class\_key&quot;:&quot;cbcde6bc26c1a0b2149b9b94d3c0f5bbe07b544fa27a27ec96aa0e8c5a0eb0bc&quot;,&quot;fact&quot;:\{&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:4\},&quot;list\_key&quot;:\{&quot;lens&quot;:&quot;method&quot;,&quot;operation&quot;:&quot;lookup&quot;,&quot;provider&quot;:&quot;platform\-web\-search\-normalized\-v1&quot;,&quot;seed\_key&quot;:&quot;svd&quot;\},&quot;rank&quot;:1,&quot;reason&quot;:&quot;same\_list\_candidate&quot;\}\]

Why found (first 3 of 5; 2 omitted; complete set in candidate evidence above):

- \{&quot;depth&quot;:0,&quot;lens&quot;:&quot;method&quot;,&quot;locator&quot;:&quot;https://rt\.http3\.lol/index\.php?q=aHR0cHM6Ly9hcnhpdi5vcmcvYWJzLzIzMTEuMTUxMjc&quot;,&quot;matched\_terms&quot;:\[&quot;video diffusion&quot;\],&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:4,&quot;relation&quot;:&quot;lookup&quot;,&quot;request&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-request:4be2cb117a8d5c2a89c1116ed73dff7b5b2d80cd15e76f22a8ecb4e77806f1e2&quot;,&quot;sha256&quot;:&quot;060f96ae2a62766721d6b2366fc52236b026ce6a5009697159b819179d6df2a4&quot;\},&quot;seed\_key&quot;:&quot;svd&quot;\}

- \{&quot;depth&quot;:0,&quot;lens&quot;:&quot;method&quot;,&quot;locator&quot;:&quot;https://scirate\.com/search?q=au%3ADockhorn\_T\+in%3Acs&quot;,&quot;matched\_terms&quot;:\[&quot;video diffusion&quot;\],&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:5,&quot;relation&quot;:&quot;lookup&quot;,&quot;request&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-request:4be2cb117a8d5c2a89c1116ed73dff7b5b2d80cd15e76f22a8ecb4e77806f1e2&quot;,&quot;sha256&quot;:&quot;060f96ae2a62766721d6b2366fc52236b026ce6a5009697159b819179d6df2a4&quot;\},&quot;seed\_key&quot;:&quot;svd&quot;\}

- \{&quot;depth&quot;:0,&quot;lens&quot;:&quot;method&quot;,&quot;locator&quot;:&quot;https://www\.emergentmind\.com/papers/2311\.15127&quot;,&quot;matched\_terms&quot;:\[&quot;training&quot;,&quot;video diffusion&quot;\],&quot;observation&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-observation:2fb96837d27557791aec39379e5c9314db5fbea16eebcb12200cacf266d0548c&quot;,&quot;sha256&quot;:&quot;5a2d0c573b3eb6282c6b2f1f7490099607968f58a1f1049bd939e19a7c6a50ad&quot;\},&quot;ordinal&quot;:3,&quot;relation&quot;:&quot;lookup&quot;,&quot;request&quot;:\{&quot;id&quot;:&quot;rw3:discovery\-request:4be2cb117a8d5c2a89c1116ed73dff7b5b2d80cd15e76f22a8ecb4e77806f1e2&quot;,&quot;sha256&quot;:&quot;060f96ae2a62766721d6b2366fc52236b026ce6a5009697159b819179d6df2a4&quot;\},&quot;seed\_key&quot;:&quot;svd&quot;\}
