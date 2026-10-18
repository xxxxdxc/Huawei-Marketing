# 本地 ZIP 与云端 ima 资料源

版本：0.3.0；日期：2026-10-18。仅修改 backend/ 和 docs/，未改 frontend/。

## 当前选择

用户选择开发默认本地 ZIP，保留云端切换。本机路径：D:/桌面/工作/比赛/浙客松/华为赛道/华为PC知识库.zip。

配置存放在 Git 忽略的 .local/settings.json；知识库压缩包位于仓库外，不复制、不解压整包、不修改原 ZIP。

- knowledge_source：local_zip 或 ima。
- local_knowledge_path：本机 ZIP 的绝对路径。
- 模型 Sonnet/GPT 仍通过原有云端模型 API 推理；本地化的是知识检索，不是模型运行。

## 切换接口

GET /api/settings 返回当前默认源、路径、local_archive_ready 和原有模型配置，不返回密钥。

PUT /api/settings/knowledge-source：

```json
{"source":"ima"}
```

```json
{"source":"local_zip","local_knowledge_path":"D:/桌面/工作/比赛/浙客松/华为赛道/华为PC知识库.zip"}
```

只切资料源，不重新提交模型名称或密钥。本地 ZIP 不存在/无效时拒绝变更，不自动转云端。

原 PUT /api/settings 增加可选 knowledge_source/local_knowledge_path；旧客户端不提交这两项时保留当前资料源。

GET /api/catalog?source=local_zip 或 source=ima 可只读预览指定源，省略 source 使用默认源。响应增加 knowledge_source/source_info。connected 表示所选资料可读取，不代表一定调用了云端 ima。前端应展示实际资料源，不能把本地成功显示成“云端 ima 检索成功”。

## 每个任务固定来源

POST /api/tasks 可选 knowledge_source；不传则使用创建时的默认源。本地任务保存 knowledge_zip_path。创建任务不读取产品正文，分析只读目录，事实和图片仍在用户确认 Brief 后读取。

- 旧任务没有 knowledge_source 时按 ima 处理；更改全局默认不会把旧云端任务改成本地。
- 本地任务后续继续读创建时绑定的 ZIP 路径；切到云端也不影响它。
- 分析时保存 knowledge_snapshot，含 ZIP 文件名、根目录版本、SHA-256、文件数与检索方式。
- 检索前验证 ZIP 指纹；替换同路径文件后，旧任务必须重新分析并确认，避免混入新版本。
- package/sources/images 标记实际来源。本地图片按指纹和原始成员路径生成独立缓存 ID，不覆盖云端图片。
- 原始资料、规划、成稿、历史记录保留；旧云端规划仍等待原用户确认。

## 本地工作方式

LocalZip 只读 ZIP 文件，复用 Ima 的指定目录原文读取、原文引用核验、图片索引/型号校验和公开价格匹配。按需将图片缓存到 .local/assets，未索引或型号不符的图片不采用。

本地搜索为目录/关键词检索，未宣称向量数据库或语义嵌入。实际引用仍限制在指定型号 P1 目录，明确商业需求才读 P1/08 公开价格快照；不以 P4 空模板或其他型号资料补事实。

本地模式不调用 ima API，也不使用其凭据；本地资料不可用时报错，不静默回退。云端模式保留原官方 ima 调用。

## 验证

- 隔离测试涵盖 ZIP 读取、目录不读正文、零网络、原包不变、索引图片型号过滤、价格按型号匹配、任务来源固定、ZIP 替换拒绝、旧设置兼容及只切资料源。
- 完整 API 链路测试使用真实构造的 ZIP 与合成模型响应，经过两次用户确认，覆盖检索、规划、写作、核验、导出；没有调用真实模型，不作为营销质量证据。
- 对用户真实 ZIP 验证：v7，1,522 文件，压缩包 26,314,860 字节；10 个产品 ID 与云端目录一致。MateBook 14 实际读取 2 份产品原文、4 张索引图片、15 条同型号公开价格快照；检索过程 HTTP 调用为 0，前后压缩包 SHA-256 相同。
- 完整证据位于 Git 忽略的 .local/local-knowledge-validation.json。原包 SHA-256：08fe08379dd2ca136f04a0971e8edc42cf2db66e8231cec638cf77cbc76de706

## 前端接入

当前页面无需新增字段即可使用新的默认本地资料源；建议设置页补 source 下拉与路径输入，任务页展示 knowledge_snapshot、source_info 和来源标记。切换控件尚未由本后端对话实现。旧前端保存模型设置不会重置资料源。

比赛运行时可用 source=ima 创建新的云端任务；本地读取结果不冒充 ima OpenAPI 调用证据。
