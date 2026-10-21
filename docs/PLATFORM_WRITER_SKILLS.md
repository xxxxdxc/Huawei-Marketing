# Platform Writer Skill 集成

确认日期：2026-10-21。保持 V3 数据与接口、两次用户确认、Writer两阶段及独立Fact Reviewer。

## 平台与阶段

| 阶段 | 小红书/朋友圈 | 微信公众号 |
|---|---|---|
| outline结构规划 | Copywriting + Social | Copywriting + Content Creation |
| draft正文生成 | Copywriting + Social + Copy Editing自检 | Copywriting + Content Creation + Copy Editing自检 |
| repair定向修订 | Copy Editing + 项目规则 | Copy Editing + 项目规则 |

自检包含在正文调用中，不额外调用模型。已有自动修订仍最多一次，之后完整独立复核。没有新Agent、主动AI润色入口或第三次确认。Planner仍只选择核心卖点。

## 实际加载方法

入口：`backend/marketing_methods.py::writer_bundle(platform,stage)`。先验证本地原文SHA-256，再按标题提取方法章节。规则覆盖写在`backend/writer_skills.md`，不是把整套上游工作流串接进应用。

- Copywriting：输入诊断、按单元打磨、收益与功能、具体表达、读者语言、一段一个论点。
- Social：Curiosity/Value Hooks、No AI Tells；排除平台快照、排期、互动监测、视频、发布流程与固定轮播模板。仅借用开头/节奏方法，小红书和朋友圈要求以项目policy为准。
- Content Creation：Blog结构与阅读方法用于outline；正文使用短段、关键信息靠前、开头与CTA位置原则。英文篇幅、H2/H3、固定3–5节和重复CTA等由项目适配规则明确覆盖。
- Copy Editing：正文只载句子、段落、AI-Tell快速检查；repair载核心点编辑原则、清晰度、语气、证据检查及快速检查。不会加载情绪强化/零风险章节，也不会把Seven Sweeps变成七次调用。
- 可选WeChat Article Writing未启用；没有引入生成封面、排版/发布或额外确认。

原文、仓库提交、SHA-256、许可证和URL见`backend/planner_sources.json`；上游文件放`backend/vendor/`，原文不改写。marketingskills为MIT，Anthropic knowledge-work-plugins为Apache-2.0，许可证保留。

## 与工作流衔接

`compose`与`draft`保持既有签名。`workflow.review`的可修复分支改为`platform_writer.repair`，继续使用`effective_plan`保留用户授权换图。结构、成稿JSON和确认接口不变。

每个Writer运行记录：stage、model、method_sources、skill_sources（仓库提交/原文哈希/章节/摘录哈希）、适配规则哈希、输入哈希、完整system提示词哈希、system+schema哈希、耗时、请求次数和服务端用量。不会记录API Key或图片base64。

修订执行程序检查：段落ID与顺序、配图必须与有效结构一致；事实ID不得超出对应段落范围；核验位置可唯一定位时，不允许改无关段落或根字段。定位为全文或不明确时，由模型按最小范围修订并由Reviewer再次全文核验。结构越界的结果不采纳，原稿保留。

最终推文继续没有内部段落标题和通用制造/测量免责声明；会改变事实结论的近似值、版本和测试条件自然保留。不以原Skill的示例数据、客户故事或试用/保证建议创造事实和权益。

## 评测

入口：`python -m backend.evals.run_writer_skill_eval prepare|before|after --folder .local/writer_skill_evals/20261021_platform_skills`。

prepare冻结现有Writer源码、方法、三组输入及图片字节哈希；baseline和after每个平台各运行一次。复用先前真实模型候选与已核验ima快照，选定卖点在运行前固定，不新检索、不重新评分；输入配对完全一致。用户授权来自本次grilling确认，不代表修改真实任务的确认。

事件与结果只写隔离评测目录，通过替换事件保存避免写任务数据库；真实调用模型并提交实际图片；核验是否完成以返回状态为准。每个arm有网络/网关核验失败且已有成稿时，最多续跑一次核验，不重新生成成稿；失败请求与耗时保留。JSON结构自动重试沿用原客户端限制并计入请求数。

评测不择优重采样，不因未通过核验丢弃稿件；分别保存初稿、修订后稿、结构、问题、耗时、模型用量及来源。逐篇质量评阅与程序引用检查分开，单次小样本不能证明稳定提升。旧15案例Planner评测不用于本轮结论。

## 首轮失败与补测口径

本轮小红书集成后首轮结构出现卖点标注与本段事实不匹配，被原有校验拒绝，未生成正文。原始CP11_after.json保留失败；提示词明确补充逐段point_ids承接规则后，只对该未生成稿做一次补测，结果另存CP11_after_recovery.json。首轮指标与补测分开，不以补测覆盖或替代首轮失败。失败结构会保存在writer_runs.rejected_outline供工作人员诊断，不采纳为有效规划。产品默认流程仍不增加自动结构重试或确认步骤。

## 自动化与服务验收

`.venv\Scripts\python.exe -m unittest discover -s backend -t . -q`：306项通过，最终一轮34.429秒。新增16项Skill专项测试覆盖三平台/三阶段路由、固定来源与路径校验、章节真实加载、可选Skill不启用、修订范围、原稿保护与修订后完整核验；原290项职责/接口/证据/发布回归保留。

本地0.6.1服务已在无BUSY任务时备份并更新；7个原任务全部GET可读，重启前后payload SHA-256一致。只读服务检查不是实际模型质量验证；真实模型结果见单独的对照报告。

真实对照结果见 [PLATFORM_WRITER_SKILLS_EVAL.md](PLATFORM_WRITER_SKILLS_EVAL.md)，包括首轮结构失败、单列补测与HTTP 524导致的复核未完成。


## 2026-10-21：成熟品牌宣传口吻

`writer_skills.md`新增`brand_promotion_v1`经验章节，包含五类截图反例、表达方法、证据边界及修订自检。outline/draft/repair沿原路由实时加载同一适配规则，第三方Skill原文和固定提交不变。`planner_sources.json`记录当前适配文件哈希。

Writer的输入投影只作用于模型请求副本，正式Brief、候选和历史版本均保留。继续提供用户需求、受众洞察、主题、已选卖点、事实条件及必须内容；去掉模型生成的策略angle、检索问题和候选推荐理由，防止把内部核对工作误当作正文任务。Reviewer诊断保留以供审计，修订提示明确要求解决风险而不照搬其建议句式。

正文、导语、图注不播报资料、不解释文章编排、不安排读者到店核对未知能力；根级CTA按原营销目标保留。已选卖点不静默删除，只有数字的薄弱点优先合并；70Wh不推导续航保证，最高功率不推导充满时间。必要约值和具体版本条件仍保留。

新写稿设置`writer_voice_version=brand_promotion_v1`，程序对明确的编排旁白、资料播报、到店核对措辞提出可修复问题，走已有一次修订和完整复核。无此标记的旧稿不会仅因新增口吻规则被追溯改写。程序匹配不能覆盖全部语义问题，实际事实与文风仍须结合独立核验及成稿评阅。接口、选点覆盖、授权配图、原有核验上限不变。

新增15项隔离测试；后端321项测试通过（40.246秒），随后图片ID逐字引用和薄弱点合并提示调整后52项Writer相关测试通过。实际截图对照另见`PLATFORM_WRITER_VOICE_EVAL.md`，不将回归通过等同于真实写作质量通过。


## 平台门店营销（2026-10-21）

适配规则新增`platform_store_v1`：公众号默认产品宣传、不写所在门店营销，可无CTA；小红书/朋友圈结尾承接当前销售人员的真实门店，缺资料采用通用引导。用户明确指定这篇公众号需要门店营销时例外，不能从旧平台到店目标自动继承。资料提取复用outline调用，不增加模型次数；draft、repair与Reviewer共用程序计算的策略。用户门店资料独立于产品事实，逐字校验出处，新稿资料变更使原审核失效。实现与回归见`PLATFORM_STORE_MARKETING.md`。
