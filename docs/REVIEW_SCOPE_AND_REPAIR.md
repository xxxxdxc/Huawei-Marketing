# 核验范围与定向文字修订优化

## 问题与结果

原问题：用户只舍弃续航和电池容量，Reviewer却将正常PPT图表称为“已舍弃主题”，要求换图并标为repairable=true；完整Document修订尝试改变image_id，被后端拦截，首次报告未作为当前报告保留。

当前处理：
1. Reviewer收到闭合review_scope，明确每个禁止主题对应的实际舍弃请求/方向。
2. “已舍弃”违规必须带scope_evidence，经程序核对主题、请求/方向编号、定位和原文/已核验画面说明。
3. 无效意见进入validation_errors/scope_audit，不当作真实产品违规，不自动删图，也不自动通过。
4. 图片问题统一停在needs_review，交由现有配图编辑后重新核验；文字修订不自动换图。
5. 模型只返回TextRepair，程序将文字修改项合并回原Document。image_id、fact_ids、heading、段落数量和顺序保持不变。
6. 首次核验报告在修订前保存。失败时原稿和首次报告保留；被拒输出写入writer_runs.rejected_output，成功或失败都记录before_review。

## 规则边界

- 普通演示文稿、柱状图、会议材料等是任务场景，不自动等同于本产品性能宣称。
- 只舍弃battery/battery_capacity，不得据此排除一般PPT图表。
- 真正出现被舍弃内容仍应报告；程序不会因为反例而白名单放行所有图片。
- 图片证据必须定位当前使用的图片，quote必须来自已核验visual_description；文件名、source路径、其他图片说明不作画面证据。
- 无法绑定或引用的意见需要再次核验/人工检查，不能自动清空后标为通过。
- 正文、图注、标题、CTA等真实客观事实仍由独立Reviewer完整核验。
- 模型原始意见保留于review.raw_model_issues，归一后的结果与原因保留于scope_audit。两个记录不能混淆。

## 内部数据结构

Issue新增可空scope_evidence；普通问题仍兼容旧格式。仅声称“已舍弃/禁写主题”的意见必须提供：

topic / request_ids / direction_ids / field / section_id / image_id / quote

field可为title、lead、paragraph、caption、image、cta、tags。topic和请求/方向必须对应review_scope。
field=image时，image_id必须等于该段当前实际图片ID。

TextRepair：
- root_changes：可选title/lead/cta/tags，null或省略表示不改，空值表示显式清空。
- paragraph_changes：按section_id提交可选text/caption。
- 不允许image_id/fact_ids/heading或未知字段；未知或重复section_id拒绝。
- 合并后仍运行原Document与定向修订校验，完整重验后才能导出。
- 实际模型传输使用TextRepair Schema。为历史直接调用/评测保留完整Document的严格旧校验分支，不允许该分支改变配图或结构。

## 工作流和界面

原端到端Document、Plan和API接口保持兼容；不增加新的用户确认。
Writer大纲/正文职责不变；仅内部repair阶段改用文字补丁。
核验模型仍为当前设置的GPT-6.1 Sol；不因此重跑Brief、Planner或Writer。
新报告含validation_errors时，界面显示“核验意见需要复核”，提供原始未采纳意见和原因；不会显示成“图片已确定违规”。
真实图片问题提示到配图编辑处理，不引导文字修订换图。

## 验证记录

隔离专项覆盖：
- 截图型PPT误判缺少绑定时被拒绝，原图不变且不会自动通过。
- 主题、请求/方向、定位、原文或画面说明不匹配。
- 真正续航越界保留，真实图片问题转人工编辑。
- 文件名不得作为画面证据。
- 修订只可改文字，未知字段/段落、重复修改和无关修改被拒。
- 首次报告和被拒输出留存，修完仍须独立完整核验。

实际测试计数、当前截图任务重验及耗时/用量见本轮.local/review-scope-guard-20261021下的结果文件和完成记录。
这里不预写“真实核验通过”，以实际运行结果为准。

## 尺寸近似限定的严格复核

仅当同一段的正文、模型所指尺寸和本段实际引用的Fact.quote都包含相同的“约L×W×H mm/cm”时，程序可确认前置约覆盖整组尺寸。数值采用不舍入的字符串规范化，单位不换算。未知/多义位置、多个尺寸链、无引用、源文没有约、数值不同或混合配置/版本等其他异议都不适用。被消除的意见仍在scope_audit中记录原文、Fact ID和判定依据，不是通用忽略事实错误。

## 本轮真实验证

截图任务3b2b20d8d97b4f40a18f6c22f5516d8c：V28暂停；修复后保留原文与图片重验，PPT/舍弃主题误判消失。新报告曾将原文与正文均已有的整组约值误判为缺少近似限定，已用上述严格规则复核已保存响应，V34为approved。复核0新增模型请求，原始响应与被消除意见完整留存。

验证脚本第一次将派生规则说明更新误当成资料改动，导致已完成的模型响应未保存；该次调用用量未留存。已修复：覆盖检查在副本执行，模型响应先保存检查点，再验证内容不变。补跑真实重验1个HTTP请求、12.757秒、27073 tokens；随后只回放该响应做程序复核，未再调用模型。不能把这次补跑描述为整个过程只消耗一次模型调用。

正文、规划、package和Writer记录与快照一致；其他任务未改变。备份及每次验证记录位于.local/review-scope-guard-20261021，均不提交仓库。

最终验证：后端448项全量回归、前端131项回归、TypeScript/Vite构建通过。本机服务已加载最终代码，截图任务V34 approved/can_export=true，公众号排版接口200且保留2张原图。
