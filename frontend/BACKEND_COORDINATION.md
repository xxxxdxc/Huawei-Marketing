# 前后端协调清单

前端变更仅位于 frontend/，已将以下需求发送给原后端对话“熟悉华为赛道提交流程”。本文件不是已实现 API 的声明。

## 已对齐：用户主动换图

用户明确确认成稿可替换当前产品 package.images 中的图片。

检查到后端已增加 record_user_image_edits / user_image_overrides，在 PUT document 记录用户换图，与模型未经允许换图区分。前端继续发送现有 {version, document}，不直接写 overrides；保存后 review 失效并重新核验。同源图片、去重和图数要求仍适用。

该项后端源码已观察到，服务运行版本和真实图文复核需要后端对话确认。前端浏览器测试验证交互和请求，不将模拟通过当作真实视觉核验结果。

## 待后续接口（当前 UI 不冒充这些能力）

1. **精细进度**：建议任务增加 stages[{key,state,started_at,finished_at,summary}]。至少区分事实提取与图片筛选，状态值 waiting/running/completed/needs_confirmation/error。前端现阶段保留六个业务阶段，但以实际 status 和结果对象显示，没有百分比或虚构阶段事件。
2. **精确问题定位**：Issue 可增加可选 section_id、field、source_id、fact_ids、image_id、text_span。当前仅在 location 与唯一段落标题或已知字段完全匹配时定位，其余展示说明并允许查看任务依据，不猜测句子位置。
3. **定向修订**：建议独立 POST /tasks/{id}/revise，带 version、issue_ids 或 instruction，返回 accepted。不得借用现有 modify 冒充定向修订，因为它会清空下游并回到 Brief。需明确修订范围、审查失效和重新核验语义。
4. **按意见重规划**：建议 POST /tasks/{id}/replan，带 version、instruction，仅在可编辑规划阶段运行；完成后回到 plan_ready，保留第二次用户确认。当前支持手工编排；更改任务目标会明确重新分析。

## 现有契约约束

- 每次写入携带 version，事件更新也可能增加版本。409 保留编辑，并要求用户决定是否放弃后载入新版本。
- 长任务使用 GET task 顺序轮询，卸载取消。无计时假进度。
- can_export + 无未保存修改 + 当前任务不在运行共同控制复制/下载；导出前再确认任务版本，并调用后端 export 校验。
- Source/Asset 展示标题、路径和说明，避免显示内部媒体 ID 与签名 URL。
- 设置页兼容公开 has_reviewer_key 字段存在时显示独立核验密钥；未存在时只提交旧契约字段。空密钥保留，保存后清空输入，不写入浏览器存储。
- 后端其他自然语言解析/追问契约如有调整，需要更新 docs/openapi.json 并明确反馈前端，避免并发改动 frontend/。
