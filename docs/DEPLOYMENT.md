# 魔搭创空间部署

目标空间：https://www.modelscope.cn/studios/Xxxxcxc/Huawei-Marketing

## 部署方式

Docker 类型，CPU 资源，服务监听 `0.0.0.0:7860`。使用单个 uvicorn worker；当前任务编排使用进程内锁和后台任务，不应简单增加 workers。生产前端构建产物由同一 FastAPI 服务提供。

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
| HUAWEI_ALLOWED_HOSTS | 创空间实际应用域名与 localhost，逗号分隔 |

魔搭访问令牌用于发布权限，不是模型服务密钥，不应作为上述业务密钥使用。本地 Windows 加密凭证文件不能复制到 Linux 容器。

## 数据与启动检查

数据默认保存 `/app/.local`；临时容器磁盘可能在重建后清空。若平台已提供持久卷，配置 HUAWEI_DATA_DIR 指向可写的挂载路径并验证重启保留；不要把数据提交到 Git。

发布检查顺序：镜像构建成功 → 服务日志正常 → GET /api/health 成功 → ima 产品目录可读 → 两次人工确认的真实任务 → 原文追溯 → 编辑使核验失效 → 重核验与导出。

真实业务验收会调用模型并消耗额度，Mock 测试不能替代上述检查。启动成功也不等于全部型号与图片均已验证。

## 发布状态

部署配置已准备；公开访问保护由后端协作接入。魔搭写入认证和云端业务环境变量需完成后才能验证真实运行。尚不宣称云端上线或真实全流程通过。
