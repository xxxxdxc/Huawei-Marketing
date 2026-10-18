---
domain:
  - multi-modal
tags:
  - 华为PC
  - 营销内容
  - 事实核验
---

# 华为 PC 营销智能体工作台

面向门店导购与营销运营人员的图文创作工作台。通过自然语言提出任务，在确认营销策略与内容规划后，依据指定 ima 产品知识库生成小红书、微信公众号或朋友圈内容，并保留事实来源与核验记录。

## 核心流程

任务输入 → 缺项补充 → **策略确认** → 资料检索与事实图片整理 → Content Planner → **规划确认** → 平台图文生成 → 核验 → 显式编辑保存与重新核验 → 导出。

- 查证前以待验证方向呈现，不把营销诉求当作产品事实。
- 资料审查未满足项优先展示；支持预览并确认局部取舍、刷新原资料源，或整体修改需求。
- 不可放弃的型号、安全与兼容性门槛仍会阻止继续。
- 编辑后原核验失效；只有服务端允许导出的版本可标识为已核验。
- Mock 只用于隔离测试，不作为真实 ima 查询或模型质量证明。

## 工程结构

- `frontend/`：React 19、TypeScript、Vite 工作台与 Playwright 测试。
- `backend/`：FastAPI 编排、SQLite 任务版本、ima 客户端、模型调用与规则核验。
- `docs/`：接口约定、资料审查与部署说明。
- `Dockerfile`：前端构建后由 FastAPI 同源服务，监听 7860。

## 本地运行

需要 Python 3.12、Node.js 22。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

打开 http://127.0.0.1:8765 。前端开发时另运行 `npm --prefix frontend run dev -- --port 5174`，Vite 将 API 转发到本地后端。

ima 使用 `IMA_OPENAPI_CLIENTID` 和 `IMA_OPENAPI_APIKEY`；对应账号需能访问项目指定知识库。模型使用 `HUAWEI_LLM_API_KEY`，独立核验凭证可配置 `HUAWEI_LLM_REVIEWER_API_KEY`。本地模式也可通过设置页保存模型凭证。

## 测试

```powershell
.\.venv\Scripts\python -m unittest discover -s backend -p "test_*.py"
npm --prefix frontend run build
npm --prefix frontend run test:ui
```

浏览器测试需要先启动 5174 开发服务。默认使用 Windows Edge；其他环境通过 `FRONTEND_TEST_BROWSER` 指定已安装 Chromium 系浏览器可执行路径。测试使用隔离数据，不会验证真实模型的营销质量或云端可用性。

## 发布

- GitHub：https://github.com/xxxxdxc/Huawei-Marketing
- 魔搭创空间：https://www.modelscope.cn/studios/Xxxxcxc/Huawei-Marketing
- 部署说明：`docs/DEPLOYMENT.md`。创建空间或上传源码不等于应用已经成功启动。

不提交 `.local/`、模型凭证、数据库、`.env`、依赖目录或本地知识库 ZIP。第三方素材与产品资料不因本项目源码发布而获得再分发许可；vendor 组件保留其原有授权文件。
