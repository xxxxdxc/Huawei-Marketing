> Writer 的平台 Skill 路由已扩展，当前实际加载方式见 [PLATFORM_WRITER_SKILLS.md](PLATFORM_WRITER_SKILLS.md)。本文的数据与确认契约继续有效。

# Planner / Writer 职责契约 V3

用户确认日期：2026-10-21。该文档取代新版任务的“Planner生成段落大纲”职责；V1/V2历史任务保留兼容。

## 职责与模型调用

- Brief、Retriever、Asset Selector、Fact Reviewer 保留原职责。
- Content Planner：一次候选模型调用，输出事实绑定、受众关联、证据/差异/图片支持评分、推荐优先级和取舍理由。优先级不是段落顺序；不输出段落、标题方向、字数分配或图位。
- 用户第二次确认的是核心卖点集合。
- Platform Writer：第一次调用只生成全文核心判断、结构理由、段落任务、承接关系、信息增量、事实及配图；程序校验通过后，第二次调用生成正文。中间大纲仅供工作人员查看，不增加人工确认。
- 独立事实核验、一次定向修复及编辑后重新核验保留。

## Skill 使用

固定上游提交与原文哈希见 backend/planner_sources.json。marketing_methods.py 在运行时校验原文并加载所选章节，不是只加载人工摘要。

- Planner：content-strategy 的 Awareness/Consideration/Decision、Customer Impact、Content-Market Fit。
- Writer 两阶段：copywriting 的 Diagnose the Situation First、Drafting Protocol、Benefits Over Features、Specificity、Customer Language、One Idea Per Section。
- 各阶段应用项目规则裁剪：单篇任务、已确认需求、证据优先、不复制示例数值、不照搬网页模板、不把内部诊断/备选稿呈现给消费者。
- social 仍归档，不参与当前调用。不引入固定四选一文章框架。

## 数据形态

`task.plan.schema_version = "3"`。

选择阶段：`phase="selection"`，`sections=[]`，`selected_point_ids`及`planning_analysis.candidates`保留；angle/cta仅为已有策略的兼容投影，title_direction为空，不由Planner另行策划。

Writer生成后：`phase="composed"`，`plan.sections`保存用于编辑、核验与导出的段落兼容结构；这不是另一份用户待确认大纲。

`task.writer_outline`：

```json
{
  "product_id": "已确认型号ID",
  "selected_point_ids": ["C1"],
  "main_takeaway": "全文让读者形成的一个判断",
  "angle": "切入角度",
  "title_direction": "题目方向",
  "composition_rationale": "全文如何推进",
  "sections": [{
    "id": "P1", "heading": "内部阅读提示", "purpose": "段落目标",
    "reader_question": "本段回应的问题", "role": "argument",
    "connection_to_previous": "为何从这里开始或如何承接前段",
    "reader_progress": "本段增加的新理解",
    "point_ids": ["C1"], "fact_ids": ["F01"],
    "image_id": "已核验图片ID或null", "image_reason": "画面关联",
    "image_position": {"kind":"after_section","order":null}, "target_chars":200
  }],
  "cta":"唯一行动引导方向"
}
```

`task.selection_confirmation={selection_hash,authorized_version,at}`；平台迁移可增加`authorization="platform_only"`。

`task.writer_stage`为`outlining`、`drafting`、`complete`，不代表Fact Reviewer已通过；失败同时查看error、resume_status和writer_runs。writer_runs分别保存outline/draft的模型、方法来源、输入/提示词/输出哈希、耗时、用量及错误。旧任务可能无这些字段。

## 接口与前端

- GET task在selection阶段返回空图片布局，不能显示成已完成的段落规划。
- POST replan-points：请求体原样兼容`{version,selected_point_ids,replace_current_plan:true}`；只保存选择，零模型调用，结果仍为plan_ready，清除旧Writer结构/确认/稿件/核验。每次勾选本身不发请求。
- POST confirm-plan：仍为`{version,plan}`。V3可以直接提交本地选中的selected_point_ids，服务器以已存候选构建可信选择，忽略客户端评分；不必先保存再确认。验证版本、型号、合法选择和必须内容后记录授权，启动Writer。V1/V2沿用历史结构确认语义。
- PUT plan：V3不接收客户端编造结构或直接替换执行卖点，允许不变内容回存，服务器保留可信分析。V1/V2继续兼容旧大纲编辑。
- 第二次确认按钮为“确认卖点，开始写稿”。Writer结构只读展示在工作人员辅助区，不显示第三次确认。
- /change-platform和/modify明确纯平台指令均可。已确认卖点复用，直接执行Writer两步和核验；未确认卖点保留选择并停在plan_ready。旧稿在版本历史中保留。Brief不重跑，不重新生成候选评分。
- 平台切换所需资料不足时沿用原补取/华为商城/图片核验规则；选中事实ID被重新抽取成不同内容时阻止静默替换。

## 校验与失败恢复

检查引用存在、型号、已选卖点覆盖、事实范围、图片可用性与重复、位置与数量、字数预算、重复问题/信息增量和必要字段。允许合并多个选中卖点到一段，也允许一个卖点跨段展开。语义是否真正连贯仍需真实内容评测，字段校验不能证明写作质量。

结构失败不进入正文，保留原选择；正文失败保留Writer内部结构；错误任务resume_status=plan_ready时可重新confirm-plan重试。评审失败保留成稿，重新review。内部标题不进入消费者预览/Markdown，通用防御性说明保留在证据区，必要限定自然表达。

## 验证边界

本次自动化回归使用隔离数据库、合成事实和模型桩，不访问真实付费模型。不把测试通过宣称为真实文案质量提升或耗时下降。此前CONTENT_PLANNER_EVAL.md为旧版冻结基准，不适用于本次职责重构后的质量结论。
