# 核心卖点确认与 Writer 两阶段前端接入

更新日期：2026-10-21。本文描述 V3 新任务；V1/V2 历史任务继续使用原有规划编辑流程，参见 PLANNER_V2_UI.md。此次前端对话仅修改 frontend/，后端实现与项目 docs/ 由原后端对话负责。

## 本地预览与启动

- 实际工作台：http://127.0.0.1:5174/ ，通过 Vite 代理连接本地后端 8765。
- 新版独立演示：http://127.0.0.1:5174/?preview=planner-v3 。可附加 &platform=wechat 或 &platform=moments。
- 旧版演示：http://127.0.0.1:5174/?preview=planner-v2 。
- 启动命令：npm --prefix frontend run dev -- --port 5174 --strictPort。

演示入口仅开发模式可用，使用模拟任务、事实、评分、SVG 插图及正文；保存、确认、切换平台均只修改本地组件状态，不向真实 API 写入，也不调用模型。演示稿未经过真实核验，复制/导出保持禁用。生产构建按真实 /api 契约工作。

## 新版操作路径

1. 第一次人工确认仍是营销策略。资料检索与缺证处理后，Planner 返回候选、排序、推荐理由和来源。
2. 第二次人工确认只确定核心卖点。默认取服务端 selected_point_ids；前端不按分数截取 Top K。勾选不发请求，页面不展示可编辑段落、叙事框架或字数预算。
3. 用户可以先“保存卖点选择”，只保存选用集合；也可以直接“确认卖点，开始写稿”，一并提交当前勾选，不需要先保存。
4. 确认后自动显示“正在安排结构与配图”与“正在生成正文”。进度取自后端 writer_stage，不以计时器推断真实服务状态。独立演示使用明确的本地模拟。
5. 自动结构在成稿区的“查看自动编排记录”中只读展示：内容主线、段落任务、前后衔接、读者进展及来源。此记录不增加人工确认，后续编辑不会自动改写初稿结构记录。
6. 成稿编辑、换图、事实追溯与重新核验保留。仅当前已核验且无未保存修改的版本允许复制或导出。
7. V3 已确认卖点切换平台时保留卖点，直接重新编排并写作；其他目标修改仍交由后端重新分析。旧稿保留在版本记录中。

## 接口与失败处理

- GET task：读取 plan.schema_version=3、phase=selection/composed、selection_confirmation、writer_stage、writer_outline。
- POST replan-points：{version, selected_point_ids, replace_current_plan:true}。在 V3 中只保存选择。
- POST confirm-plan：{version, plan}。plan.selected_point_ids 取当前本地选择，服务器验证可信候选及必要需求；客户端不重算评分。
- POST change-platform：{version, platform}。V3 采用此专用接口；旧任务继续兼容原修改接口。
- 选择为空、超过 8 个或包含未知候选时给出提示并禁止提交。必要需求覆盖、型号与事实约束由服务端最终校验。
- 保存/确认失败保留本地选择；409 保留输入并要求显式载入最新版本。
- Writer 失败时保留已选卖点；即使 phase=composed，error + resume_status=plan_ready + selection_confirmation 仍提供“重试编排并写稿”。
- composed 历史选择保持只读；不能把 Writer 结构当成待确认规划或伪造核验通过。

## 文件分工

- PointSelection.tsx：V3 选择状态、可选保存、直接确认和失败重试。
- PlanEditor.tsx：按版本分流，保留 LegacyPlanEditor 与公共图片选择器。
- PlannerAnalysis.tsx：共用候选、推荐理由、评分及来源；V3 不显示旧大纲关联。
- DraftEditor.tsx / WriterStructure.tsx：Writer 真实阶段、结构追溯、平台切换及既有编辑/核验。
- TaskView.tsx / WorkflowProgress.tsx：核心卖点标签、写作阶段导航和状态文案。
- types.ts：V3 phase、确认授权及 Writer 字段，兼容缺少这些字段的历史任务。
- SelectionPreview.tsx / selectionPreviewData.ts / main.tsx：开发专用隔离演示。
- qa/planner-writer-v3.spec.ts：12 项专项浏览器回归。
- qa/planner-writer-visual.cjs：新版选择、成稿、结构和手机预览截图。

## 验证记录

- npm --prefix frontend run build：TypeScript 与生产构建通过。
- npm --prefix frontend run test:ui：98 项全量回归通过（1.5 分钟），包含 12 项新职责测试与 86 项既有测试。末轮提示文案/演示编号调整后，12 项专项再次全部通过（17.7 秒）。
- 实际运行 Edge 隔离浏览器并目视检查：1440px 桌面、390px 手机，卖点确认操作区、成稿双栏、移动预览及自动结构。专项 axe 基础无障碍与无横向溢出检查通过。额外截图检查无 pageerror、无 API 写请求。
- 按 web-design-guidelines 当前规则检查控件标签、可见焦点、原生勾选/折叠、异步反馈、长文本与减少动画设置；修正“先保存再确认”的误导文案与 V3 空候选提示。
- 后端原对话更新服务后，只读 GET 5174/api/health 返回 200；8765/openapi.json 版本 0.6.0，confirm-plan、replan-points、change-platform 均存在。
- 当前 qa/results.json 是最近一次 12 项专项结果；截图位于 qa/screenshots/planner-v3-*.png，均为本机忽略文件。

本轮未对真实任务提交选择、确认、切换平台或触发生成，未验证真实文案质量，未推送或部署。

### 纯平台切换中的资料适配

已确认卖点切换平台时，plan可暂时为空。前端现使用服务端platform_selection和当前platform_only授权识别资料适配，保持六步、原确认完成及写作工作区，原卖点只读可查。详细字段与验证见[PLATFORM_ADAPTATION_UI.md](PLATFORM_ADAPTATION_UI.md)。
