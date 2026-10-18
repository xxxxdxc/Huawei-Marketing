# 魔搭创空间部署

目标空间：https://www.modelscope.cn/studios/Xxxxcxc/Huawei-Marketing

## 部署方式

Docker 类型，使用当前空间可用的免费 CPU 资源 platform/2v-cpu-8g-mem，服务监听 `0.0.0.0:7860`。使用单个 uvicorn worker；当前任务编排使用进程内锁和后台任务，不应简单增加 workers。生产前端构建产物由同一 FastAPI 服务提供。

Dockerfile 使用 Node.js 22 构建前端；Python 3.12 运行后端，并保留 Node.js 执行 ima 客户端脚本。依赖由前后端锁文件安装。

## 私密环境变量

在创空间设置中配置，不能写入公开 README、ms_deploy.json、Dockerfile 或 Git 历史。

| 变量 | 用途 |
| --- | --- |
| IMA_OPENAPI_CLIENTID | ima OpenAPI 账号 Client ID |
| IMA_OPENAPI_APIKEY | ima OpenAPI 密钥 |
| HUAWEI_LLM_API_KEY | 理解、规划与写作模型凭证 |
| HUAWEI_LLM_REVIEWER_API_KEY | 可选独立图片理解与核验凭证；省略时沿用写作密钥 |
| HUAWEI_LLM_BASE_URL | 可选 HTTPS 模型服务地址，须与密钥配套 |
| HUAWEI_ALLOWED_HOSTS | 本空间代理会改写 Host，云端设置为 *；本机默认仍限制 localhost 与 127.0.0.1 |

魔搭访问令牌用于发布权限，不是模型服务密钥，不应作为上述业务密钥使用。本地 Windows 加密凭证文件不能复制到 Linux 容器。

## 数据与启动检查

数据默认保存 `/app/.local`；临时容器磁盘可能在重建后清空。若平台已提供持久卷，配置 HUAWEI_DATA_DIR 指向可写的挂载路径并验证重启保留；不要把数据提交到 Git。

发布检查顺序：镜像构建成功 → 服务日志正常 → GET /api/health 成功 → ima 产品目录可读 → 两次人工确认的真实任务 → 原文追溯 → 编辑使核验失效 → 重核验与导出。

真实业务验收会调用模型并消耗额度，Mock 测试不能替代上述检查。启动成功也不等于全部型号与图片均已验证。

## 发布状态

2026年10月18日已通过 Git 推送并完成免费 Docker 部署，平台状态 Running。构建、依赖安装、前端打包及容器启动通过；公开创空间中的嵌入工作台可加载，隔离浏览器未发现页面脚本错误。首页与健康接口返回正常，云端 ima 目录真实读取到 10 个型号。写作模型为 claude-sonnet-5-5，核验模型为 gpt-6.1-sol，凭证通过平台私密环境变量注入。

本次仅验证部署、页面及只读目录；没有创建真实营销任务，没有运行云端生成、人工确认和核验导出的完整业务闭环。当前尚未实现公网访客任务隔离、共享设置保护及调用限额，不能据此视为多租户生产版本。

请从 https://modelscope.cn/studios/Xxxxcxc/Huawei-Marketing 进入；平台嵌入页会携带访问参数，不要把带访问参数的临时页面地址提交到源码。自动化只读检查使用平台返回的 API 专用域名并通过发布令牌认证。
