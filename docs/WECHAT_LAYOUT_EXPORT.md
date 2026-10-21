# 微信公众号排版与手动导入

范围：已核验公众号成稿的排版预览、富文本复制、HTML 导出、顺序图片包。没有微信API、凭据配置、自动上传、草稿创建或发布；不增加模型调用。

## 使用方式

公众号稿件核验通过并保存后，点击编辑器底部“公众号排版与复制”。
选择摸鱼绿（默认）或摸鱼票据；标题与正文分开复制，分别粘贴到公众号标题栏和正文编辑器。
图片缺失时下载“顺序图片包”，按图片顺序.txt 标出的段前/段后位置补插。

在线复制提供 text/html 和 text/plain；不支持 ClipboardItem 时尝试原生选区复制。
拒绝复制时显示失败及手动选择入口，不把纯文本降级伪报为排版复制成功。
复制前重新检查最新任务版本及核验指纹。软件内的本地图片地址不会自动变成微信素材，不能保证跨平台粘贴后图片完整。

HTML单文件包含内联样式与嵌入的原图，供离线查看；微信可能过滤data URI。
ZIP含 article.html、preview.html、title.txt、原始图片、图片顺序.txt、manifest.json、使用说明.txt。
图片按文章使用顺序命名，记录 section_id、段前/段后、图片说明、sha256。
ZIP是导出时的核验快照，内容修改后必须回软件重新核验。

## 接入与职责

Brief → 检索/事实和图片核验 → Planner卖点选择 → Writer结构和正文 → Fact Reviewer → 当前通过稿件 → 公众号排版/复制/导出。

backend/wechat_export.py 是确定性导出适配器，仅公众号调用，不把新Skill拼进Writer Prompt，不改变Writer两次调用或其他Agent职责。
复用workflow.can_export、storage.digest、effective_plan、effective_layout。
状态approved、review.passed=true、指纹一致、version与最新版本一致才准入。
图片须属于已核验图片池，型号和画面通过、未被拒用；验证实际图片格式和已有源SHA后按当前布局导出。
原Markdown、图文包、小红书和朋友圈链路保持兼容。

html仅包含原导语、正文、图片说明、CTA和话题标签；标题单列。
不输出Paragraph.heading、step/tool-label、章节编号、目录、评级/星级、作者占位、附加互动尾注。
逐块逐字符核对原文，逐项核对图序与原图字节；检查允许标签、属性、样式，并执行上游固定版本验证器。
上游ERROR阻塞；标点WARNING记录并提示工作人员，为保持审核原文不自动改标点。

## 原版Skill的使用

来源：https://github.com/isjiamu/gzh-design-skill
固定提交：ba1f4175519b481cb3566616c9e5178705067904
位置：backend/vendor/gzh-design-skill
许可：AGPL-3.0-or-later；保留上游完整LICENSE和版权。

只取“产品测评/工具盘点”方法：
- 摸鱼绿：全局容器、正文、tool-card基本容器、image容器、绿色下划线。
- 摸鱼票据：全局容器、正文、key-point-card容器、image-ticket容器、绿色下划线。
- 运行时从原版组件读取内联样式并验证来源SHA；参数强调只包裹原文现有子串，每段最多两处。
- 不运行上游的章节/评分/作者/目录生成规则；没有改动上游原文件。
- 适配器及预览源码注明许可、修改日期和范围；预览页提供白名单排版组件源码下载，包含上游完整源文件与许可证，不含任务/凭据/.local。
- 未擅自修改主项目其余文件的许可证声明。

## 接口

三个任务接口都要求version正整数；theme可选moyu-green或moyu-ticket，默认moyu-green。

GET /api/tasks/{tid}/wechat/render?version=N&theme=moyu-green
返回title/html/plain_text/assets/document_hash/html_sha256/theme/source/checks/warnings。
html是正文片段；图片URL为当前应用的/api/assets/{id}。

GET /api/tasks/{tid}/wechat/preview?version=N&theme=moyu-green
带CSP的预览页，标题和控制栏在正文复制范围之外。

GET /api/tasks/{tid}/wechat/export?version=N&theme=moyu-green&bundle=false
下载可离线查看的HTML正文片段；bundle=true下载预览与顺序图片ZIP。

GET /api/wechat/layout-source
下载排版组件源码和许可；仅白名单文件，无任务数据/凭据/环境配置。

错误：版本变动409，非公众号/未通过当前核验/缺图或字节变动等400，缺少version或主题不支持422。
所有接口不保存任务或历史版本。

## 验证范围

后端422项全量回归通过，其中20项为公众号专项；收尾新增2项边界回归后，22项公众号专项再次通过。
前端完整128项回归通过，其中6项为本轮入口专项；TypeScript/Vite构建通过。
独立Edge18项通过，覆盖实际HTML/plain剪贴板、本地contenteditable原生粘贴、两主题、图序、图片下载、复制拒绝恢复、旧版本拦截、1440/390px无障碍和无横向溢出。截图已目视检查。
真实任务库91条记录前后哈希一致。已有一份通过核验的公众号稿件在本机新接口返回200和两张原配图；未重跑任何Agent。

未调用真实模型、未写入公众号，也未验证已登录微信后台实际粘贴；本地编辑器通过不等于微信兼容性已通过。

复现：
- python -m unittest backend.test_wechat_export
- frontend目录：npm run test:ui -- wechat-export.spec.ts
- python -m backend.evals.serve_wechat_preview --port 8767 --info .local/wechat-layout-qa/fixture.json
- frontend目录：node qa/wechat-export-smoke.cjs

测试服务强制使用TEMP目录、拒绝模型调用。回归先导入隔离fixture再导入后端并断言DB路径在TEMP，禁止把测试数据导入真实任务库。
