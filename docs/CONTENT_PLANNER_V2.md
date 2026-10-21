> 当前新版职责已迁移：请以 [PLANNER_WRITER_RESPONSIBILITIES.md](PLANNER_WRITER_RESPONSIBILITIES.md) 为准。以下保留历史设计供追溯。

# Content Planner V2 设计与接口说明

> 当前接口以 [PLANNER_POINT_SELECTION.md](PLANNER_POINT_SELECTION.md) 为准：仅两种方法来源，取消强制叙事框架，新增明确选用与大纲重编排。下文保留初版V2设计记录及其冻结评测背景。

更新：2026-10-21。范围为单篇华为 PC 图文策划；Brief、检索、事实提取、图片筛选、Writer 和 Reviewer 的核心职责保持原状。

## 现有问题与改进

旧版一次调用直接给出 angle/title_direction/sections/cta，缺少可检查的候选取舍与评分依据；purpose 混合写作目标和读者问题；叙事结构隐含在段落顺序里；每段 image_id 不能表达公众号段前/段后、小红书封面和朋友圈图格位置。已有程序验证引用集合、图片唯一与数量，但缺少候选到段落的证据链以及段落重复检查。

新版流程：已确认 Brief + 可执行证据范围 → 输入证据检查 → Sonnet 候选生成 → 程序评分排序 → Sonnet 叙事及段落规划 → 程序校验 → 用户第二次确认 → 原 Writer/Reviewer。只生成规划，不生成软文。平台更改仍从 Planner 重做；不会重跑 Brief。

## 方法来源

参考 community `coreyhaines31/marketingskills`，固定提交 `e85f3cbc2e4a79bf33b2a12e9bdd9087d414735b`。三份原始 SKILL.md、轮播参考和 MIT 许可证保存在 backend/vendor/marketingskills，source.json 保存文件哈希。

| 来源 | 提炼方法 | 本项目适配 |
| --- | --- | --- |
| content-strategy | 受众问题、购买阶段、内容取舍 | 只做一篇内容，不做选题日历、SEO与投放计划 |
| copywriting | 先明确读者要解决什么，再连接事实和利益、安排信息层级与CTA | 只做写作目标与标题方向；保留“约、典型值、配置条件”，不产出成稿 |
| social | 平台原生结构、单一重点、图序与CTA | 使用本项目小红书/公众号/朋友圈规则，不照搬海外平台要求 |

模型只读取裁剪后的 backend/planner_adapter.md 和阶段提示，不直接拼接三份完整 Skill。Skill 是策划方法，不能成为产品事实来源。

## 数据结构

保留原 Plan 的 angle、title_direction、sections、cta。原 PlanSection 的 id、heading、purpose、fact_ids、image_id、image_reason 全部保留。旧历史记录和旧格式请求仍可读取/保存。

V2 增量字段：

- schema_version: "2"；product_id 与任务和知识包一致。
- narrative: framework（scene_story / problem_solution / buying_guide / selling_point_focus）、reason、ordering_rationale。
- selected_point_ids：本篇实际承接的候选编号。
- sections 增加 reader_question、role、point_ids、image_position、target_chars。purpose 是写作目标；argument/objection 必须有候选与事实引用。
- planning_analysis：服务端只读审计。包含 candidates、weights、status、warnings、input_hash、based_on_hash。候选含 direction、audience_need、fact_ids、image_ids、conditions、四项 scores（value 0..4 + reason）、total_score、rank。

总分 = audience×35/4 + evidence×35/4 + differentiation×15/4 + image×15/4，满分100。分数是模型策划判断，服务端重算总分；不是营销效果预测，也不是产品参数。“差异性”指本篇取舍的辨识度，不允许无依据竞品领先。事实卡限定条件由服务端合并，模型不得通过省略条件提高评分。

图片布局 image_position：

| 平台 | 有图 kind | order | 展示方式 |
| --- | --- | --- | --- |
| wechat | before_section / after_section | null | 当前段前/段后 |
| xiaohongshu | carousel | 从1连续的整数 | 第一张封面，按序轮播 |
| moments | grid | 从1连续的整数 | 按序图格 |
| 无图 | none | null | 不占用图片位置 |

新增 task.planner_runs 记录阶段耗时、模型、提示/输入/输出哈希、候选排序及调用用量，不包含密钥。task.render_layout 是按有效规划与实际文稿图片推导的布局。不得让模型自评成为可信事实。

## 校验与能力边界

输入复核原文摘录、事实编号、型号、冲突、图片型号与视觉核验。候选只能引用本包事实/图片；不得重复编号；证据0分拒绝，无图支持的图片分必须0；模型返回错误 product_id 拒绝。段落不能引用未入选候选或超出候选的事实；入选候选必须被承接。论证/疑虑段不能无事实。不同段落重复同一读者问题拒绝，高文本相似度提示人工检查。

图片不得重复；序号必须连续唯一；平台布局类型、图数和篇幅预算必须满足要求。平台预算：朋友圈80–150，小红书300–500，公众号600–900字。target_chars 是策划预算，不冒充实际成稿字数。用户舍弃范围在新增执行字段中继续检查，候选审计历史不作为可执行内容。

程序能证明编号存在和结构约束，不能证明每个营销利益的语义都由原文推出，也不能凭图片ID证明图文语义匹配。这两项由证据提示、用户确认及原有事实/图片 Reviewer 继续把关；评测同时做独立语义盲评。

## 编辑、兼容与导出

接口路径和请求壳不变：PUT /api/tasks/{id}/plan 和 POST /confirm-plan，仍为 {version, plan}。旧请求省略V2字段时，从原保存结构按section_id继承；旧记录不强制迁移。手动更改后保留规划与历史评分，但标记 user_modified；原评分和叙事判断不再宣称代表当前内容。客户端不能伪造服务端候选分数。

前端支持读者问题、段落角色、图位置/顺序编辑，并显示候选排序与原评分的失效提醒。增删、撤销与调整段落会归一图片顺序。用户换成稿图片后继续使用已授权 user_image_overrides，核验前不允许最终导出。

Writer 接收执行规划，不接收候选自评分。Reviewer 接收有效布局。预览和 Markdown 使用同一图序约定，ZIP 增加 layout.json。Markdown 是阅读顺序投影，不保证第三方平台导入后自动还原原生轮播/九宫格；layout.json 保留结构。

## 评测复现

基线：backend/evals/planner_baseline.json，冻结自 d51df77 的提示、原字段与约束。独立 LegacyPlan 契约不使用更新后的 Plan（类名不同，字段约束一致）。

准备：`.venv/Scripts/python.exe -m backend.evals.prepare_planner_materials <私有ima材料目录>`。
执行：`.venv/Scripts/python.exe -m backend.evals.run_planner_eval --materials <目录> --output .local/planner_evals/runs/<run>`。

案例在 backend/evals/run_planner_eval.py 固定为5类需求×3个平台，共15例，均使用真实ima原文和经模型核验的图片；输入快照哈希、随机顺序、盲评分配和评分标准在运行前写入 manifest.json。每例旧版一次、新版一次，新版包含2次Sonnet调用。每对1次独立GPT盲评，匿名A/B且不展示版本、模型名或候选自评分。盲评统一比较两版共有的角度、目的、事实与图片字段；新增结构完整度单独测试，避免以字段多自动加分，也意味着该盲评不直接评价全部V2元数据。没有最终文案生成或发布操作。

原始证据、模型输出和失败诊断保留在被git忽略的.local中。统计失败不能从分母剔除；一次运行不能证明质量稳定性或线上用户效果。真实耗时取完整方案调用时间，新版两阶段通常增加时延。模型返回的usage与response_model按实记录，不把模型别名当作底层模型身份保证；资料准备与额外失败尝试单独披露。


首轮15例真实对比的完整结论见 [CONTENT_PLANNER_EVAL.md](CONTENT_PLANNER_EVAL.md)。


2026-10-21 追加：对外自然表达、内部段落标题及证据导出分离规则见 [PUBLICATION_COPY_RULES.md](PUBLICATION_COPY_RULES.md)。旧稿正文不自动重写；此前15例评测为这些规则加入前的冻结版本。


## 候选选用与编排职责更新（2026-10-21）

本版取消强制叙事框架，只用content-strategy/copywriting做取舍和编排。新增候选推荐理由、composition_rationale及POST /replan-points；执行集合与前端待更新勾选分离，失败保留原大纲。具体字段、错误状态、旧数据兼容见 [PLANNER_POINT_SELECTION.md](PLANNER_POINT_SELECTION.md)。上述更新优先于本文此前版本描述，旧评测结果不覆盖本版。
