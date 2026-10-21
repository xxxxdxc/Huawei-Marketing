# 纯平台切换的前端阶段适配

更新日期：2026-10-21。用户已确认保留六步流程，资料适配作为写作阶段内的临时状态；不增加确认节点。本次只修改 frontend/，不更改后端职责或接口。

## 行为

- 只换平台时，已确认卖点显示完成，工作区停留在“图文与核验”。
- 旧 plan 临时清空、后端 status=planning/retrieving 时，显示“适配新平台资料”，不显示为重新生成候选或重新确认卖点。
- 资料适配后使用真实 writer_stage：outlining 为结构编排，drafting 为正文生成；完成后按原核验与导出门槛工作。
- “核心卖点”和写作区的折叠记录读取服务端原确认快照，只读展示选中项及原事实摘录/来源编号/限定条件，不把它伪造为新平台已核验结果。
- 适配失败仍保留确认记录，提供查看资料问题及明确“重试平台资料适配”。重试使用已有 POST /replan {version}，不重新确认策略或卖点，不自动触发。
- 未确认卖点不显示为已完成；首次规划、普通资料刷新与旧任务保持原行为。

## 识别依据

不能只凭 plan=null、status=planning 或 selection_confirmation 判断。后端 platform_change.apply 在开始适配时会同时清空 plan、selection_confirmation、writer_stage。

platformPresentation.ts 使用当前 platform_selection 快照，并检查：

1. 最近 platform_changes 的目标平台与当前平台一致；
2. brief_confirmation.authorization=platform_only；
3. analysis_hash 与当前 brief_analysis_hash 和确认记录一致；
4. authorized_version 与确认记录一致且不晚于当前任务；
5. 没有更新的 evidence_refreshes、point_replans 或 resolution_history 取代本次操作。

确认完成只来自 platform_selection.confirmed===true。原选择来自 platform_selection.plan.selected_point_ids，原依据来自 platform_selection.facts。后端正常完成切平台后仍可能保留快照，因此这些检查用于避免将后续普通刷新误标为切平台。

## 文件

- src/platformPresentation.ts：平台上下文、确认快照及阶段映射。
- src/ConfirmedPointRecord.tsx：只读原确认卖点及证据。
- src/types.ts：声明后端已有的可选平台快照、授权和历史字段。
- src/TaskView.tsx、WorkflowProgress.tsx：流程、页签、状态、导航与错误位置。
- src/DraftEditor.tsx、PlanEditor.tsx、shared.tsx：适配状态、只读记录、失败入口及避免误归类为新缺证。
- src/style.css：记录区域、长原文和移动布局。
- qa/platformAdaptationFixture.ts、platform-adaptation.spec.ts：隔离数据与15项专项回归。

## 验证

先用隔离任务复现旧版错误：plan为空时未出现平台适配界面。修复后15项专项全部通过，全量122项浏览器回归通过（1.9分钟），TypeScript及Vite生产构建通过。

覆盖刷新加载、六步保持、只读原确认及证据、适配→结构→正文→核验、明确重试、409锁定、更晚的三类操作、哈希/目标不匹配、未确认选择、首次规划、同状态快速失败切换、1440px/390px axe与无横向溢出。

已实际打开Edge隔离浏览器，目视检查桌面与手机的适配状态、确认完成标记、原卖点与展开依据。新增截图检查单独1项通过。按web-design-guidelines检查语义按钮/原生折叠、可见焦点、阶段反馈、长文本与响应式。截图及完整测试报告位于Git忽略的qa/screenshots/：platform-adaptation-*.png、platform-confirmed-points-*.png、platform-adaptation-full-results.json；qa/results.json为最后单独截图检查。

## 边界

数据与阶段变化由隔离Mock提供，不是新一轮真实模型调用或真实任务写操作。磁盘后端源码已只读核实相应字段和/replan契约，本轮检查时8765未运行，已通知原后端对话处理服务恢复；前端仅启动5174，没有代为启动后端。当前测试不能声称真实平台切换端到端已重新验收。未推送或部署。
