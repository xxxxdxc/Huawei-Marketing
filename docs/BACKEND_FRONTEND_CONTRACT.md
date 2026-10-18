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
