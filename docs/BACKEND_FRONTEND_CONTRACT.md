> 新版 Planner / Writer 职责及接口差异见 [PLANNER_WRITER_RESPONSIBILITIES.md](PLANNER_WRITER_RESPONSIBILITIES.md)，V3 内容以该补充契约为准。

# 前后端接口补充：成稿换图复核

更新日期：2026-10-18。后端由原对话维护；本文不要求前端改后端文件。

## 已实现：用户成稿换图

沿用 `PUT /api/tasks/{id}/document`，请求仍为 `{version, document}`，无需额外的确认标志或新接口。用户在界面明确选择图片并点击保存即可；禁止把模型输出自动送到此接口伪装成人工授权。

后端会：

1. 对比上一次保存的成稿和本次成稿，只记录实际变更的图片位置；仅改文字，不会顺带授权模型之前偷偷更换的图片。
2. 拒绝不属于当前产品 `package.images`、`model_verified` 未通过的图片；拒绝重复使用同一图片，以及不满足当前平台图片数量的编辑。当前接口要求保留规划段落编号和顺序。
3. 保留原 `plan` 作为原始用户确认记录，新增只读 `task.user_image_overrides`，按 section_id 记录 image_id、original_image_id、product_id、origin、authorized_at、authorized_version。origin 为 user_document_edit。前端不能通过请求直接提交或伪造这些记录。
4. 保存后清除 review，状态为 needs_review；当前版本不能复制为最终稿或导出。调用原 `POST /review`，请求 `{version}`，等待完整复核。
5. Reviewer 使用应用用户授权换图后的有效规划，并检查新图的实际画面、来源、型号、图文匹配和合规；不会仅因为与原始 plan 图片不同就判错。核验通过才允许最终导出。
6. 没有用户操作记录的模型换图仍按违规处理。再次修改文字保留有效换图记录；换回原规划图片清除该位置的覆盖。重新确认策略、重新规划或更改任务会清除旧覆盖。历史恢复沿用对应历史状态，但旧核验仍失效。

HTTP 400 表示图片、段落或数量约束未通过；HTTP 409 表示 version 过期，请重新读取任务。校验失败不保存部分编辑。

## 现阶段能力边界

- 还没有独立的“定向修订接口”；`/modify` 仍是修改任务并回到 Brief，不要包装成保留现有规划的一键修复。
- 还没有独立的“带意见重规划接口”。
- status/events 当前只提供联合阶段与真实事件；不应推断未实际提供的逐模块完成百分比。
- Issue 当前只有 category/location/detail/severity/repairable；尚无 section_id/source_id/fact_id/span。可对确定匹配的 location/heading 定位，不宜猜测精确文字位置。
- 设置接口已支持独立 reviewer_api_key，详见 FRONTEND_HANDOFF.md 第 12 节。

## 验证

30 项后端隔离测试通过，包括用户换图、未授权模型换图、跨产品/未核对图片、重复图片、数量不足、撤销换图、Reviewer 有效规划和确认策略清除旧授权。没有改动 frontend/，没有为本次验证调用付费模型。


## Brief V2（2026-10-18）

后端已新增官方 Campaign Plan 适配、三阶段编排、自然语言可选选择器入口、来源标记、结构化追问回答、确认哈希与实际检索计划。完整接入说明见 [BRIEF_V2_CONTRACT.md](BRIEF_V2_CONTRACT.md)。

GET task 保留旧 brief 投影，并增加 brief_analysis/brief_analysis_hash/brief_confirmation/dialogue/brief_runs。未知平台时旧 brief 可以为 null；新前端应从 brief_analysis 展示问题。创建任务可以只提交 raw；新增 POST /tasks/{id}/brief/answers。confirm-brief 支持 {version,analysis_hash}；旧客户端编辑策略卡后提交会重新分析、要求再次确认，不会直接检索。不能假定所有 confirm-brief 202 都已启动检索，应读取实际状态。

本轮不修改 frontend/。前端自然语言入口和新版 Brief 展示仍需前端对话接入；不能将后端可用等同于页面已接入。

最终验证：57 项后端隔离测试通过；真实 Sonnet 已验证自然语言追问/回答、ready 与 needs_resolution。运行服务已更新为 0.2.0。范围与证据见 [BRIEF_V2_VALIDATION.md](BRIEF_V2_VALIDATION.md)；本轮未进行真实图文全链路生成。


## 0.2.1：已省略商业信息不阻塞

通用到店 CTA 不强制询问门店/城市；明确价格优惠请求进入检索，缺失或冲突时自动省略并继续，不增加确认弹窗。新处置见 package.content_policy 与真实 events；原始 evidence status 不变，核心产品冲突仍暂停。详见 BRIEF_V2_CONTRACT.md 的 0.2.1 节。若展示省略说明，应放在任务说明/提醒中，不拼入营销正文。


## 0.2.2：逐项降级与旧阻塞任务恢复

价格有依据、优惠缺失时保留价格；仅用户明确“该项缺失就不生成”的原话构成商业阻塞条件。普通“必须写”不阻塞，模型 required 不等于用户硬约束。详见 BRIEF_V2_CONTRACT.md 的 0.2.2 节。

新增 POST /tasks/{id}/resume-plan {version}，让已有检索资料但尚无 plan/document 的 needs_review 任务按当前规则继续规划，原确认和资料保留；并非通用 replan。前端可提供恢复按钮，本轮仍未改 frontend/。content_policy 新增 omitted_categories/blocked_requests，提示与实际状态一致，不将省略说明写入营销正文。


## 0.3.0：本地 ZIP 默认、任务资料源固定

新增 knowledge_source=local_zip/ima 和 local_knowledge_path；用户已选开发默认本地。切换接口 PUT /api/settings/knowledge-source，仅影响新任务，保留模型设置和凭据。GET catalog 返回实际来源与 ZIP 指纹，不能把本地读取标为 ima 在线检索。

POST tasks 可指定来源；不传使用创建时默认。旧任务继续云端，新本地任务固定 ZIP 路径和版本，切换全局不会混用。前端原有请求仍兼容；建议补资料源选择及来源展示，完整约定和验证见 LOCAL_KNOWLEDGE.md。frontend/ 未修改。


## 0.4.0：纯平台切换与商城补充

详见 [PLATFORM_CHANGE.md](PLATFORM_CHANGE.md)。新增 POST /api/tasks/{id}/change-platform {version,platform} 与 /replan {version}；已确认 Brief 的纯平台修改不重跑 Brief，完成后仍停 plan_ready。旧 /modify 固定平台按钮指令兼容。新增 platform_changes、package.asset_candidates、package.supplement_attempts。商城条目 knowledge_source=vmall，任务原 knowledge_source 保持不变；须按条目展示真实来源。未改变 direction_id→request_id→coverage 的关联语义。前端按钮旧文字“重新分析/回到策略确认”应更新为“重新规划/确认新规划”。


## 0.5.0 资料审查局部取舍与重查

接口与完整请求/响应示例见 [EVIDENCE_RESOLUTION.md](EVIDENCE_RESOLUTION.md)。新增 GET /api/tasks/{id}/evidence-review、POST /evidence-resolution/preview、POST /evidence-resolution/confirm、POST /refresh-evidence（后3项均在 /api/tasks/{id} 下）。预览只读；确认需 version、preview_id、confirmed=true 及受影响约束的明确授权。复用资料后停 plan_ready，不自动写稿。原始 Brief/确认哈希/coverage 保留；execution_scope 和 resolution_history 单独记录。取舍边界贯穿规划、写稿、核验、修订与手动编辑后的核验。任务级上传未实现，补入原 ima 或替换固定路径 ZIP 后使用 refresh-evidence；该入口实际重取资料并接受新 ZIP 快照。/modify 整体变更仍失效当前各阶段产物；/replan 与 /resume-plan 不作为任意降级接口。FactRequest 新增可选 depends_on、waivable、guardrail，不改写历史已确认 Brief。


## 0.5.1 模型输出错误与核验恢复

详见 [MODEL_OUTPUT_RECOVERY.md](MODEL_OUTPUT_RECOVERY.md)。核验失败的 GET task.resume_status 统一为 needs_review，兼容历史错误记录（只读投影），前端现有“重新核验”可只调用 /review {version}。已有稿件不再因核验错误被引导回 /confirm-plan 重写。结构错误明确到字段/截断/空响应并给本机诊断编号；API预扣额度不足单独提示，不能当作内容审核失败。没有初稿的写稿错误仍保留 plan_ready。


## Content Planner V2（2026-10-21）

原Plan字段与接口继续兼容，新增候选审计、叙事、段落读者问题和图片位置。详细字段、旧客户端编辑行为及layout.json约定见 [CONTENT_PLANNER_V2.md](CONTENT_PLANNER_V2.md)。规划和成稿仍须分别确认，用户编辑后仍需重新核验。


## 对外文案与内部阅读提示（2026-10-21）

paragraph.heading继续用于工作人员定位，不进入实际推文预览、复制或marketing.md。ZIP新增evidence.md保留完整证据，单独Markdown为对外正文。新稿publication_policy_version=natural_copy_v1应用自然限定、内部说明隔离与CTA去重规则，旧稿正文不自动迁移。详见 [PUBLICATION_COPY_RULES.md](PUBLICATION_COPY_RULES.md)。


## 候选选用与编排职责更新（2026-10-21）

本版取消强制叙事框架，只用content-strategy/copywriting做取舍和编排。新增候选推荐理由、composition_rationale及POST /replan-points；执行集合与前端待更新勾选分离，失败保留原大纲。具体字段、错误状态、旧数据兼容见 [PLANNER_POINT_SELECTION.md](PLANNER_POINT_SELECTION.md)。上述更新优先于本文此前版本描述，旧评测结果不覆盖本版。


## 平台门店营销（platform_store_v1）

不新增前端设置页或确认步骤。门店资料由本次自然语言提供；后端在现有Writer大纲调用中提取，保存在只读任务字段`store_marketing_context`（details逐字值+turn_id/quote，及可选wechat_exception）。`writer_outline`可额外包含同结构的`store_context`；旧响应缺少这些字段仍有效。所有产品事实/配图/段落接口不变。

公众号默认无所在门店营销，`plan.cta`和`document.cta`可为空字符串；预览、复制、导出应自然忽略空CTA，不生成占位文案。用户明确要求这篇公众号加入门店营销时例外。小红书/朋友圈在既有根级`cta`承接门店，缺资料用通用门店引导，有真实店名时使用该店名。继续不在产品正文插入门店核对、试用指导或内部段落标题。

切换平台按当前平台重算，保留门店资料和确认卖点，不调用Brief；仅有门店资料或继承到店目标不构成公众号例外。新写稿设置`store_marketing_version`，门店资料变更纳入审核哈希；旧稿不自动改写，旧审核哈希保留兼容。详见`PLATFORM_STORE_MARKETING.md`。


## 公众号排版与手动导入（2026-10-21）

新增公众号专用的已核验稿件导出适配，不改变任务/Writer协议。接口及错误码见 [WECHAT_LAYOUT_EXPORT.md](WECHAT_LAYOUT_EXPORT.md)。前端仅在公众号任务 can_export、没有未保存修改且未锁定时允许打开 /api/tasks/{tid}/wechat/preview?version=N。新页面完成主题选择、富文本复制、HTML及顺序图片包下载。所有在线复制/导出检查最新版本与审核指纹。无微信API或自动发布。


## 核验范围与文字修订（2026-10-21）

Document/Plan及所有写入端点保持兼容；内部repair改为TextRepair，只输出文字/图注修改项，图片、事实编号和顺序由程序固定。review新增可选validation_errors、scope_audit、repair_decision、raw_model_issues/raw_model_summary。validation_errors非空时不可导出，显示核验意见需复核；图片问题进入现有配图编辑。原始意见和程序复核依据保留。首次报告和失败修订输出不再丢失。细节见[REVIEW_SCOPE_AND_REPAIR.md](REVIEW_SCOPE_AND_REPAIR.md)。


小红书配图：至少 1 张不同的已核验图片；3–6 张仅作推荐，不因偏离推荐范围阻塞、强制补图或删图。公众号与朋友圈数量规则不变。

旧小红书任务兼容：仅接受按原 `min_images=3,max_images=6` 平台 policy 计算的精确候选上下文哈希；需求、事实及图片等上下文仍须一致，不能借规则升级沿用变化后的旧候选。
验证：453 项后端回归、29 项相关浏览器回归及 TypeScript/Vite 构建通过。截图任务保留原 Brief、资料与卖点，以两张图完成 Writer 和独立核验（V53 approved）。本机恢复记录位于忽略目录 `.local/image-count-recovery/`。


手动补充文字依据：`POST /api/tasks/{tid}/manual-evidence`，请求与处理限制见 `MANUAL_EVIDENCE.md`。审查 actions 新增 manual_evidence；原 refresh-evidence 仍只重读原资料源。新增 Source.source_type=user_manual、source_url、link_verified=false，以及 Review.source_verification；旧数据和接口保持兼容。

coverage.status 新增 partial，fact_ids 保留已有支持；missing_details、usage_limits 为工作人员说明。不要将 partial 渲染为“没有直接依据”或“全部已核实”；普通检索条件部分缺失可继续，真实 guardrail/冲突和用户明确完整条件要求仍处理。写作规则卡仅在 writing_boundaries/all_facts 追溯，不进入可宣传事实。


## 2026-10-22：资料处理步骤恢复与临时模型错误

`GET /api/tasks/{id}` 增加可空只读字段 `prewrite_recovery`：`stage`（source_retrieval / fact_extraction / image_review / selling_points）、`label`、`resumable`、`reason`。仅失败且尚无规划或成稿的任务可恢复；不应根据 HTTP 文案猜测失败模块。

使用 `POST /api/tasks/{id}/retry-prewrite`，请求 `{version}`，返回 202。保留已确认 Brief，从对应步骤继续；图片阶段不重新检索或提取事实，卖点阶段不重新核图。成功后停在卖点确认，不能自动写稿。恢复前校验策略确认、型号、原文、事实、图片与取舍的检查点指纹；输入变化、缺少原文、过期版本或运行中状态拒绝恢复。

旧任务可根据最后一个真实阶段事件识别图片核验失败；历史中的旧 Planner 错误不能覆盖后续图片失败。前端显示“重试图片核验”等实际阶段按钮；没有完整覆盖结果时不伪装成资料缺口或要求重新分析需求。

模型调用的总尝试次数最多 2 次，包含格式修正与临时失败重试。408 / 500 / 502 / 503 / 504 / 520 / 522 / 523 / 524 及连接、读取超时，首次失败等待 1 秒再试；401 / 403 及已识别额度错误不重试。重试可能产生额外模型费用，不能保证上游服务恢复；二次失败保留当前步骤。事实、图片与合规校验维持原规则。


## 2026-10-22：摘录与首次商城补充

详见 [EVIDENCE_INGESTION.md](EVIDENCE_INGESTION.md)。Package 保留 `quote_repairs`（原摘录及真实连续原文定位）、`rejected_facts`、`unresolved_fact_ids`、`omitted_product_requests`、`supplement_attempts` 等只读审计。普通检索priority不等于文案必写；仍执行已确认的真实门槛。华为商城逐来源标记，不冒称来自ima；原事实ID保持，新来源增量加入。

### CTA 阶段与平台边界

Brief 的 `message_strategy.cta_direction` 作为兼容字段保留，新分析写入空字符串；营销目标和用户原话仍保留。schema 3 的 selection 阶段 `plan.cta` 为空，只有 Writer 的 composed 阶段生成 CTA 文案。公众号默认 product_only，大纲中未授权门店 CTA 会记录并清除后继续，合法产品收尾保留；正文仍须修订和完整复核。明确的公众号门店授权继续支持，小红书/朋友圈无门店资料使用通用邀请。历史 Brief 不回写，旧 CTA 不作为新授权。
