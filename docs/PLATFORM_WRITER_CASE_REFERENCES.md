# Platform Writer 用户指定案例经验库

本轮用户确认：仅启用以下四篇作为方法学习对象，其他24个研究候选保持归档，不加载进Writer。不是独立成效认证，也不补造评分或互动量。

| 案例 | 来源 | 可用方法 |
|---|---|---|
| C019 | https://diy.zol.com.cn/1153/11537575.html | 需求判断标准、角色定位 |
| C020 | https://article.pchome.net/content-2192863.html | 选购困难切入、具体任务承接 |
| C021 | https://mobile.adquan.com/info/detail-333811 | 统一场景主线、动作连接产品 |
| C022 | https://www.gamersky.com/hardware/202411/1844493.shtml | 单次自然门店收尾 |

## 加载方式

`backend/writer_skills.md`为本项目适配规则，`backend/references/platform-writer/cases.json`为案例清单。`backend/writer_cases.py`校验来源、路径及卡片字节哈希，只提取当前阶段的方法段落，再由`marketing_methods.writer_bundle`送入实际system prompt。outline、draft、repair分别加载主线、表达、局部修正方法；`writer_runs.case_sources`记录链接、访问范围、本地文件及摘录哈希，便于追踪。

公众号：C019+C020+C021；小红书：四篇；朋友圈：C021+C022。例外公众号门店任务仍按现有平台政策处理，不因是否加载C022而阻塞。未加载案例不会改变既有Copywriting、Social、Content Creation及Copy Editing路由。

原有两次写作调用、独立核验、定向修订、选点覆盖和事实图片校验不变。没有新确认步骤，没有修改其他Agent职责，没有前端改动。

## 证据与边界

来源均为公开网页文章或活动分析，不伪装为三个目标平台的原生帖子。PChome只依据此前读到的开头和部分正文，上轮重访超时，不分析未读结尾；其余三篇已在集成前实际读取主要正文。图片未观察，不推断图文结构，也不下载或复用第三方图片。

方法经验不包含参数、价格权益、个人体验或门店资料；事实仅来自当前任务证据。公众号默认无门店营销，社交平台仅根级cta承接一次；工作人员内部分类不变成公开段落标题。用户截图观察单独记录，不作为第五个外部案例。

第一阶段研究的run_manifest是历史记录，不代表本轮仍未修改后端。候选表历史快照在research/platform-writer-cases/archive。本轮只做隔离回归，不声称已经用真实模型验证文案质量提升，也未部署到魔搭。

## 本轮验证

完整后端隔离回归：402项测试通过，39.475秒。新增12项案例库测试覆盖白名单、平台/阶段路由、卡片完整性、路径边界、实际system prompt与来源审计；保持两次Writer调用加独立核验，修复仍为现有单次定向修订。没有调用真实模型，不声称文风改善已获实测。验证清单见`research/platform-writer-cases/writer_integration_validation.json`。
