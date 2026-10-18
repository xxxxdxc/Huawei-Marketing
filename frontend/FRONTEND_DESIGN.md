# 华为 PC 门店图文助手：前端设计与验收

本次范围仅为 frontend/。既有 React 19、TypeScript、Vite、Lucide 与 CSS 工程继续使用。接口保持同源 /api，未引入生产 Mock 或外部产品图。

## 设计决策

- 浅灰底、白色工作面板、深蓝 #2446A8 主强调色；字号、边框、圆角和焦点统一。
- 左侧新任务/历史/连接设置，任务顶部显示产品、人群、场景、平台与版本。
- 人群和场景可从自然语言任务中提取，创建页的补充字段可选；作为 raw 里的明确补充内容交给后端，最终由用户确认。
- 两次明确确认：营销策略 -> 查证资料；内容规划 -> 写作核验。
- 规划为可编辑段落卡，支持上下移动/拖动、移除与撤销、事实引用、当前型号配图。
- 桌面编辑/预览双栏；1050px 以下切换编辑和预览；手机采用可关闭的导航面板。
- 小红书图片翻阅+短文、公众号分节长文+段内图、朋友圈简文+网格图片。更换目标平台调用 modify，重新走策略确认，不伪装为仅更换皮肤。
- 正文显式保存。输入立即取消当前页面的已核验表述并禁用导出；保存后服务端使旧报告失效，重新核验后才可交付。
- Fact/Asset 原文弹层使用原生 dialog，支持 Escape、焦点约束和返回。引用保留原文与限制条件，图片仅使用 /api/assets/{id}。
- 不把无问题条目当作独立通过证明；报告依赖后端 can_export，未保存内容显示报告已过期。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| src/App.tsx | 工作台导航、任务加载、顺序轮询、API错误、409重新载入、离开保护 |
| src/StartPage.tsx | 任务输入、可选补充、型号和平台、连接与目录异常 |
| src/TaskView.tsx | 同一任务内切换、上下文、历史恢复、修改任务目标 |
| src/WorkflowProgress.tsx | 六个业务阶段展示，仅映射后端可确认状态 |
| src/StrategyEvidence.tsx | 首次策略确认、原位补充信息 |
| src/PlanEditor.tsx | 大纲编辑、事实选择、图片选择与数量检查 |
| src/Evidence.tsx / Dialog.tsx | 资料浏览、原文标记、图片来源、无障碍弹层 |
| src/DraftEditor.tsx | 显式保存、换图、版本门槛、重新核验、复制和下载 |
| src/PlatformPreview.tsx | 三种实质不同的平台阅读预览 |
| src/ReviewPanel.tsx | 报告分类、问题详情、可定位编辑位置、实际事件记录 |
| src/SettingsPage.tsx | 本机模型连接设置，密钥输入保存后清空 |
| src/shared.tsx | 同源请求、错误类型、公共表单与图片组件 |
| src/style.css | 统一视觉与响应式布局 |
| qa/fixtures.ts / qa/workbench.spec.ts | 隔离浏览器验收数据与测试 |

## 启动与检查

在 frontend 目录执行：

```powershell
npm ci
npm run dev
npm run build
```

后端由其负责对话启动在 127.0.0.1:8765；前端默认 5173，Vite 代理 /api 到后端。不要为了前端改动终止或重启后端。

浏览器验收需要另一个终端启动 5174：

```powershell
npm run dev -- --port 5174 --strictPort
npm run test:ui
```

默认测试浏览器为本机 Microsoft Edge。其他机器可设置 FRONTEND_TEST_BROWSER 为 Chromium/Chrome/Edge 的绝对可执行路径。

## 验证边界

- 浏览器测试全量拦截 /api，请求与响应都在 Playwright 中模拟，不访问真实模型、不创建真实任务、不保存真实密钥。
- 测试中的产品、参数、图片和核验结论均明确为模拟；模拟图为测试脚本生成的图形，只存在于请求拦截中，不在生产包中。
- qa/screenshots 的模拟截图带水印。真实服务只读截图以 live- 开头，不能当作真实生成验收。
- `npm run build` 是类型与生产构建检查；axe 是自动无障碍检查，并非完整人工无障碍认证。
- 真实模型生成质量、费用、图片推理与完整链路仍由后端联调确认。所有导出均以服务器当前版本门槛为准。
- 仓库现有成果未提交；本次没有提交或推送 Git。

接口协调及暂不支持能力见 BACKEND_COORDINATION.md；本次执行结果见 qa/QA_REPORT.md。

## 2026-10-18 对话入口与圆润视觉更新

按用户确认的参考方向更新：浅冷灰背景、白色大圆角输入区、100px 轻导航、深色胶囊主按钮、圆润线条图标及少量柔和彩色场景入口。沿用系统中文字体，蓝色用于焦点和选中状态。首页不展示六阶段；需求对话及策略确认后，才进入原阶段工作台。

- StartPage.tsx：自然语言输入为主，型号与平台可选；场景卡只填入示例，不发送。目录暂不可用时可先提交描述。
- BriefConversation.tsx：读取 V2 权威需求、真实 dialogue 和已记录问题；支持部分回答、选项和自由输入；标注明确/推断/待明确，卖点仍为待查证。
- StrategyEvidence.tsx：V2 优先，兼容旧任务策略编辑；首次分析反馈放在对话中。
- App.tsx：未选择的型号/平台不传；保留版本冲突和未保存保护；窄导航图标具有可访问名称。
- TaskView.tsx：需求阶段显示对话，确认后展示阶段工作台。后续两次确认、证据省略/阻塞、显式保存、复核和导出规则保留。
- types.ts、style.css：补齐 Brief V2 类型和全站圆润视觉、手机布局。
- qa：新增自然语言创建、V2 部分回答、409 输入保留、服务端 hash 确认、移动端键盘与无障碍测试。

接口：/brief/answers 携带 version 和 question_id；/confirm-brief 使用服务端 brief_analysis_hash；需求调整仍调用 /modify。未修改后端。测试场景均标记为模拟，实际前端不注入模拟数据。

## 资料检查暂停后的处理（后端 0.5.0）
知识库依据顶部默认显示未满足需求；明确已找到/缺少/影响。选择舍弃项后先请求服务端只读预览，再展示保留、删除、依赖影响和剩余门槛；需要放宽原拒绝条件时，用户逐项勾选。显式确认后停在内容规划，保持规划确认。资料补充页显示真实 ima 或固定 ZIP 位置，手动更新后调用 refresh-evidence。整体需求修改提示原结果失效范围并返回策略确认。
代码：EvidenceResolution.tsx、evidenceResolutionTypes.ts；TaskView/App 接入；StrategyDirections/EvidenceCoverage 同步 execution_scope。仅用后端提供的关联与取舍结果，不在前端解除证据门槛。
