# Planner / Writer V3 验证记录

日期：2026-10-21。实现契约见 [PLANNER_WRITER_RESPONSIBILITIES.md](PLANNER_WRITER_RESPONSIBILITIES.md)。

## 后端自动化

命令：`.venv\Scripts\python.exe -m unittest discover -s backend -t . -q`

最终结果：290 项测试通过，用时43.949秒。运行使用临时数据库、合成证据和模型桩，不调用真实模型。新增职责专项模块含21个测试方法，其中无效结构测试覆盖10种子情况。

覆盖：Planner仅生成候选；保存选择零模型调用；可直接确认本地选择；客户端评分不可覆盖服务器记录；没有授权不能启动Writer；Writer先结构后正文再独立核验；非法事实/图片/型号/卖点/预算/布局在正文前拦截；多个卖点可合并成一段；问题和信息增量重复检查；失败保留选择、结构及阶段日志；重试；编辑后失效核验；已确认平台迁移跳过Brief与候选生成；未确认选择停在确认处；旧V1/V2兼容；最终推文不包含内部结构标签。

结构测试不能证明语义连贯或真实文案质量。没有本次真实模型前后对照数据，也没有真实模型耗时改善结论。writer_runs会在后续实际调用时分阶段记录耗时和用量。

## 本地服务只读核对

- 服务：127.0.0.1:8765，API版本0.6.0，OpenAPI包含V3 Plan。
- 重启前无运行中任务；SQLite备份：`.local/writer-split-backup-20261021-170802.sqlite3`。
- 6个既有任务全部GET可读；重启前后数据库任务payload SHA-256完全一致。
- 日志：`.local/writer-split-server.stdout.log`、`.local/writer-split-server.stderr.log`。
- 没有创建真实营销任务或提交真实模型请求；没有推送GitHub或部署魔搭。

## 前端验证

前端由专门对话仅修改frontend，结果与截图见frontend/qa/QA_REPORT.md及该对话的本次验证记录。后端本次没有替代前端执行其浏览器验收。

前端专门对话报告：生产构建通过，98项完整浏览器回归通过；已检查桌面/手机模拟流程并只读核对0.6.0接口。该结果来自前端对话执行，后端对话未独立重复运行。
