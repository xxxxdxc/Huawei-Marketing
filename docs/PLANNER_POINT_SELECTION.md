> 当前新版职责已迁移：请以 [PLANNER_WRITER_RESPONSIBILITIES.md](PLANNER_WRITER_RESPONSIBILITIES.md) 为准。以下保留历史设计供追溯。

# 候选卖点选用与大纲重编排契约

更新：2026-10-21。仅后端与契约文档；前端由另一个对话负责。没有推送、部署或真实模型任务。

## Planner 职责和方法

运行方法只来自固定版本的 content-strategy 与 copywriting：取舍候选内容、梳理读者问题/利益与信息层级、安排段落/事实/图片。social 原文只保留为旧评测的归档材料，不进入当前方法适配。平台图数、篇幅预算和图位置来自项目契约。

不生成具体文案，不替 Writer 设计写作Skills。取消四种 narrative.framework 的强制选择。新模型输出 composition_rationale，用简短文字说明为什么这样编排；旧 narrative 保留读取兼容，不再要求新增此字段。

## 返回字段

保持 plan.schema_version="2" 及 angle/title_direction/sections/cta。新增/明确：

- plan.composition_rationale: string，新增模型必填1–1000字；旧记录可缺省，GET只读投影从旧 narrative.ordering_rationale/reason 提取，不写回数据库。
- plan.selected_point_ids: string[]，当前大纲实际执行的集合，不是前端未提交的勾选状态。
- plan.planning_analysis.candidates[].recommendation: "recommended" | "alternative"。
- recommendation_reason: string，解释推荐或暂不采用的原因；分数仅辅助，不机械TopK。
- candidate.request_ids: 通过事实覆盖关联的检索请求；candidate.mandatory_need_ids: 对应已确认Brief中用户明确必须内容的编号。
- analysis.mandatory_needs: 只读的 id/text/field/evidence 列表；analysis.method_sources 为 ["content-strategy","copywriting"]；analysis.candidate_context_hash 绑定需求、资料和平台契约。
- planning_analysis 由服务端维护；客户端不能通过PUT或confirm-plan改写分数、推荐或候选证据范围。

初始生成仍两阶段：候选/评分/推荐 → 按推荐集合编排。朋友圈1、小红书2–3、公众号3–4只是建议，不是硬性限额；用户可选择1–8个真实候选。资料少时不凑数，明确必须内容多时不能以推荐数为由静默丢弃。段落/图片数量与篇幅仍须通过平台契约。

必须内容只来自已确认Brief的明确来源（source=explicit，带“必须/务必/不能遗漏”等含义的正向要求）以及已确认“缺少价格/优惠就不生成”的商业条件。普通检索 priority=required 不等于该卖点必须写进文案。禁止性约束仍沿用 execution_scope 和事实核验；缺价默认省略规则保持不变。

必须需求的语义关联由模型在候选阶段标注，程序验证其编号、候选证据、选择覆盖和实际段落承接；不宣称仅凭编号就能证明自然语言语义完全正确。旧候选若缺少新必须需求的标注，需重新规划候选，不能静默跳过。

## 显式更新接口

POST /api/tasks/{tid}/replan-points

请求：

    {
      "version": 12,
      "selected_point_ids": ["C1", "C3"],
      "replace_current_plan": true
    }

replace_current_plan 必须明确为布尔true；缺失、false、1或字符串均拒绝。数组1–8项，不得重复或引用不存在的候选。

成功接受：HTTP202，{accepted:true,task_id:"..."}。不直接返回新规划，沿用GET /api/tasks/{id}轮询。

- 仅plan_ready（包括保留原规划的可重试状态）允许请求，先确认Brief仍有效。
- 请求开始生成新版本，status=planning；原plan及其selected_point_ids保留，pending_point_replan记录请求集合。
- 只进行一次段落编排调用（底层已有结构失败重试机制不变），不调用Brief、检索、选图或候选生成评分模型。候选再次校验事实/图片/需求快照，不重新取资料。
- 模型必须严格回显请求的选用集合，并在段落实际承接每个候选；多选、漏选、未知事实、图片不合规或缺少必须内容均不采纳。
- 成功时替换plan，清空旧document/review/成稿换图覆盖，status=plan_ready、error=null，等待原有第二次确认后才写稿。旧规划保留在版本历史。
- 运行失败：status恢复plan_ready、error说明原因，原plan、其执行集合及已保存编辑保持原样，pending清空。可携最新version明确再次请求；不会自动无限重试。
- 服务重启发现该操作中断时，同样恢复plan_ready并保留原规划，不自动调用模型。
- 前端未保存编辑由前端保留，后端不会假装持有它们。请求202并不表示模型成功，前端须检查后续status/error和实际plan。

错误：400 为未知/重复候选、缺少必须内容、来源/快照变化、不允许的状态等；409 为version过期；422 为请求结构或明确替换标志错误。前置验证拒绝不改变任务版本，不调用模型。

## 手动编辑和第二次确认

PUT /plan 与 POST /confirm-plan 请求壳不变。可修改段落标题、目标、事实、配图等；只要仍在原选用范围，不再因普通编辑清空 point_ids。

不能通过这两个接口替换 selected_point_ids；换集合须走 replan-points。无论 analysis.status 是否 user_modified，段落只能引用已选候选及其真实事实，每个选中候选都须有实际事实承接；不能仅挂编号或改成opening来绕过。删除最后承接段需调整大纲，不能静默删掉执行卖点。新增旧格式段落省略point_ids时仅从当前选中候选内推导，不能扩展范围。

旧版没有可信候选的手工规划仍按原接口验证事实/图片；不会制造假分数。旧V2候选只有通过数据库来源、当前证据引用、型号和可用性复核后才能重用。历史projection不覆盖保存的原始候选元数据。

## 验证

backend/test_point_selection.py 覆盖：非TopK推荐、朋友圈建议非硬限额、单次编排无其他Agent调用、异步保留原大纲、严格替换确认、版本并发、选用范围、必须内容、普通检索优先级不锁选用、失败/中断恢复、历史兼容、手动编辑和分数防伪造。

所有测试使用隔离夹具与mock模型。本次未做真实推理或重跑旧的15例盲评，不将此前评分作为本版质量证据。
