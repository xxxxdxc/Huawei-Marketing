# 仅修改目标平台：后端 0.4.0

日期：2026-10-18。仅修改 backend/ 与 docs/；未修改前端。

## 行为

仅变更平台且 Brief 已确认：保留型号、人群、需求、营销目标、核心策略、检索计划和明确约束。确定性更新 canonical Brief 平台字段，添加对话证据，记录原确认和新授权哈希，不调用 Brief Parsing / Audience Insight / Marketing Strategy。旧规划、文稿、核验失效，历史版本完整保存。

新平台的语气、篇幅、结构、图数规则优先于保留策略中沿用自旧平台的表达指导。Planner 可以重排和取舍卖点，但不得新增未经证据支持的结论。完成后停在 plan_ready，仍需用户确认规划才写稿、核验和导出。

已有材料足够时：复核证据覆盖、复用实际文件 SHA256 一致的已核验图片，只调用一次 Planner。不重新读取整个知识库，不重新提取事实。

不足时：使用知识库中精确型号对应的商城商品链接，尝试从华为商城补充。新增图片经过画面核验；新增原文与原知识库原文共同提取事实并检查覆盖与冲突。不能用新平台切换绕过原来的证据门槛。

## 接口与现有客户端兼容

推荐接口：

~~~http
POST /api/tasks/{id}/change-platform
Content-Type: application/json

{"version": 27, "platform": "wechat"}
~~~

platform 仅 xiaohongshu / wechat / moments。version 严格校验；运行中、未确认 Brief、相同平台拒绝。返回 202 后轮询任务。

现有前端无需改请求即可使用快捷分支：/modify 中原有固定按钮指令“将目标发布平台改为微信公众号，保留产品型号、人群和营销目标，重新应用该平台的内容与配图规则。”已兼容；精确短句“改成公众号”等也兼容。带其他需求的指令、歧义指令或尚未确认的 Brief 仍走原需求分析路径，不用模型猜测是否仅改平台。

前端后续应将按钮文案改为“更换平台并重新规划”，说明从“回到策略确认”改为“确认新规划”。可直接接入专用接口。后端没有修改 frontend/。

补资料后重试：

~~~http
POST /api/tasks/{id}/replan
Content-Type: application/json

{"version": 31}
~~~

仅限当前 Brief 的平台变更授权仍有效且尚无文稿的重规划任务。可从材料不足或异常状态重试，不再次调用 Brief；不能绕过新规划确认。

## 数据与取证

- platform_changes：from_platform / to_platform / turn_id / original_analysis_hash / analysis_hash / original_confirmation / authorized_version / at。
- brief_confirmation.authorization = platform_only；原授权留在 platform_changes 和历史版本中。
- package.asset_candidates：保存筛选前候选及评估，包括拒绝素材；不把候选全集误称为全部已核验图片。
- package.images：当前已通过筛选的可用图片。
- package.supplement_attempts：商城尝试时间、结果、商品链接、实际取证 URL、SSR/API 方式、SKU、新增来源和图片编号。
- 商城 source/image.knowledge_source = vmall；任务 knowledge_source 仍表示原本地 ZIP 或云端 ima。前端必须按条目显示商城来源，不能把补充材料显示成 ima 原文。
- source.id、fact.source_id、检索请求 id/direction_id 和 coverage.request_id 的既有关联语义不变。重新提取事实后事实编号可能变化，旧 plan/document 已清除，不能继续引用旧事实编号。

## 商城范围和限制

只匿名读取官方已知商品页及公开商品 API，不登录、不购买、不爬取评价。精确核对商品型号、鸿蒙/Windows 类别、SKU和明确配置约束；不选择近似型号代替。只下载对应 SKU 商品图库的官方图片，不从全页递归收集推荐商品或用户图片。

商品资料读取入口：商品页 Next.js SSR；公开 queryDisplayProductByVersion API 为备用。图片只从 res.vmallres.com 读取。页面/API/CDN 跳转均检查白名单；响应大小、时间、图片格式和像素有上限。

原需求没有价格优惠时，不向事实提取模型加入独立价格优惠字段。用户要求时记录页面 SKU、渠道、采集时间及资格/地区状态；预估价不作为门店成交价，缺少活动期或资格的优惠不能视为已支持。

价格优惠仍按请求逐项降级：缺证默认提示并省略；仅用户明确“缺少就不生成”才阻塞。已有价格不会因优惠缺失被连带删除。关键产品证据冲突或缺失、必要图片不足仍暂停。商城访问或精确型号映射失败时记录缺口，不自动去其他网站。

## 验证

完整离线回归：127 项通过，其中新增平台/商城测试 30 项。模型响应和大部分 HTTP 为显式 fixture，不是营销质量评分。

真实只读验证：本地 MateBook 14 鸿蒙版映射到官方商品 SKU 2801010196914，读取 10 项主要参数并成功下载 1 张官方商品图；未请求价格时未输出 commercial_snapshot。该图片只完成格式、尺寸和来源读取验证，未在本次真实验证中调用视觉模型。记录位于 Git 忽略的 .local/platform-vmall-validation.json。未修改任何现有用户任务，也未发布内容。
