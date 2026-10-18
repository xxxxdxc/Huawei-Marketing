# 资料审查暂停后的解决接口 — 0.5.0

日期：2026-10-18。所有接口只操作明确指定的任务；开发验证不自动确认、舍弃或生成任何现有真实任务。未修改 frontend/。

## 三条路径

1. 调整内容继续：读取局部取舍预览 → 用户确认保留/删除/关联影响及受影响的拒绝降级条件 → 复用合格资料和已核验图片 → 重新规划 → 停 plan_ready，等待用户确认规划。
2. 补充依据再检查：先在任务原资料源补充资料，再显式 refresh-evidence，重新读取目录、原文、图片并检查。保留历史和当前已授权取舍。
3. 重新描述需求：原 /modify 保留。修改产品/人群/目标等整体要求，会失效当前 Brief、确认、资料包、规划、文稿、核验、执行取舍，重新分析并确认策略。resolution_history 及历史版本留档。

/replan 仍限明确的平台变更；/resume-plan 仍限已有缓存、无规划和文稿的旧规则重新评估，不能替代任意内容降级授权。

## 读取审查概览

GET /api/tasks/{id}/evidence-review

示意响应（裁剪字段；ID以服务端实际返回为准）：

~~~json
{
  "version": 18,
  "knowledge_source": "local_zip",
  "knowledge_snapshot": {"kind": "local_zip", "sha256": "..."},
  "unmet_requirements": [
    {
      "request": {"id": "R1", "question": "续航是否满足课程需要", "priority": "required"},
      "coverage": {"request_id": "R1", "status": "not_found", "fact_ids": [], "reason": "缺少测试条件"},
      "found": [],
      "missing": "缺少测试条件",
      "affected_direction_ids": ["D1", "D3"],
      "blocking": true,
      "omitted": false,
      "can_drop": true
    }
  ],
  "available_facts": [{"id": "F01", "claim": "已有依据的重量事实"}],
  "material_requirements": [
    {
      "request_id": "R1",
      "type": "product",
      "target_model": "已确认完整型号",
      "conditions": ["具体配置"],
      "document_types": ["续航表现的官方说明、参数与测试/适用条件"]
    }
  ],
  "task_upload_supported": false,
  "actions": ["adjust_content", "refresh_evidence", "modify_requirements"]
}
~~~

未舍弃的阻塞需求排在前面；返回当前资料源、本地包路径（local_archive_path）、目标型号、所需资料类型和适用条件。前端可以默认展开，但不能把原始 supported 当作最终成稿核验通过。

## 只读预览

POST /api/tasks/{id}/evidence-resolution/preview

~~~json
{"version": 18, "drop_request_ids": ["R1"], "drop_direction_ids": []}
~~~

同一方向只是请求分组，不等于彼此依赖。舍弃一个请求仅传播到显式 depends_on、已冲突的共享证据及旧 Brief 请求自身的主题依赖，不反向删除它的前置请求，也不因为分组标题相同而删除独立请求。必要型号核查作为前置依据保留；直接舍弃身份、安全或必要兼容请求仍阻塞。方向仅剩身份核查时不再用于营销；同方向还有独立卖点时，以保留请求重建本次执行方向，原始 Brief 不变。比如舍弃“续航”会影响“轻便和续航兼顾”，但不因组合方向被删就反向删除独立的重量依据。主题匹配是保守规则，完整影响必须在确认前展示。续航表现与电池容量、充电性能分别处理；舍弃高续航不等于删掉已有独立电池容量事实。

~~~json
{
  "task_id": "...",
  "version": 18,
  "preview_id": "E...",
  "selected_request_ids": ["R1"],
  "selected_direction_ids": [],
  "omitted_request_ids": ["R1", "R3"],
  "omitted_direction_ids": ["D1", "D3"],
  "removed": [{"request": {"id": "R1"}, "coverage": {"status": "not_found"}, "dependency": {"kind": "selected_or_inherited", "via": "R1"}}],
  "affected_directions": [{"direction": {"id": "D3", "direction": "轻便和续航兼顾"}, "request_ids": ["R3"], "selected": false, "reason": "直接选择或关联请求/主题/证据依赖"}],
  "retained": [{"request": {"id": "R2"}, "coverage": {"status": "supported", "fact_ids": ["F01"]}}],
  "retained_fact_ids": ["F01"],
  "excluded_fact_ids": [],
  "excluded_image_ids": [],
  "remaining_blockers": [],
  "required_constraint_acks": [],
  "prohibited_topics": ["battery"],
  "prohibited_topic_labels": ["续航表现"],
  "can_apply": true,
  "next_status": "plan_ready",
  "requires_plan_confirmation": true,
  "requires_asset_review": false,
  "original_brief_hash": "...",
  "original_coverage": []
}
~~~

removed、affected_directions、retained 返回完整原结构。原始 coverage 不变，未将缺证伪造成 supported。preview 不保存任务、不增加版本、不读资料源、不调用模型或生成文稿。preview_id 绑定任务、version、选择范围、证据包、对话及当前执行边界；任务、范围或材料变化必须重新预览。空选择可用于只读查看当前阻塞，不能据此授权空内容。

## 显式确认局部取舍

POST /api/tasks/{id}/evidence-resolution/confirm

~~~json
{
  "version": 18,
  "drop_request_ids": ["R1"],
  "drop_direction_ids": [],
  "preview_id": "E...",
  "confirmed": true,
  "acknowledged_constraint_ids": []
}
~~~

只有用户明确确认后才能调用。不要自动提交预选确认。若预览 required_constraint_acks 返回 requires_ack=true 的条件，必须展示原话并由用户逐项勾选本次放宽，再将对应 id 提交。已授权的同一条件不会要求重复授权。普通 required 不等于用户拒绝降级。

接受后 HTTP 202：

~~~json
{"accepted": true, "task_id": "..."}
~~~

状态：needs_review/plan_ready → planning → plan_ready；若实际图片核验不通过或仍有门槛，停 needs_review；异常保留中间状态为 error。不会自动写稿，沿用 POST /confirm-plan 的用户确认。运行中拒绝确认。过期 version/preview_id 返回 409；未明确确认、未授权约束、剩余门槛等返回 400；字段类型不合法返回 422。

## 保留原始证据与执行边界

- brief_analysis、brief_confirmation 及确认 hash 不原地改写。
- resolution_history 保存原请求、原确认、原始 coverage、证据指纹、完整预览、授权版本、时间和约束授权。
- execution_scope 为独立派生执行边界，包含 omitted_request_ids / omitted_direction_ids / prohibited_topics / excluded_fact_ids / acknowledged_constraint_ids。传入模型的 boundary 还包括 relaxed_constraints 原话及请求范围，明确哪些原拒绝条件已被本次授权放宽，其余硬条件不变。
- package.coverage 为原始报告，仍可见 not_found/conflict。
- package.all_facts/all_conflicts 留存原始事实与冲突；package.facts/conflicts 为当前安全执行范围。
- package.execution_coverage 为当前执行范围的覆盖视图，不能用它替代原始覆盖。被隔离的事实只会降低支持状态，不会把失败改成成功。
- Planner/Writer/Reviewer/修订均收到派生 Brief、scope 和过滤后的事实。写稿模型不收到 all_facts/all_conflicts；不得因原文仍存在就恢复已舍弃主题。
- 文本规则扫描标题、导语、正文、图注、CTA、标签中的已舍弃主题；独立模型核验负责同义改写和画面。有限关键词规则不是完整语义证明。
- 已核验图片画面描述明确含已舍弃主题时，预览列入 excluded_image_ids；新增/未核验图片按实际需要核验，缓存图片字节不一致阻塞。
- 成稿手动编辑后的重新核验继续执行 scope；scope 本身计入导出指纹。纯平台切换重新绑定执行边界，保留最初授权来源；整体 /modify 则清除当前 scope。

## 不能绕过的门槛

产品身份不明或错配、原始证据结构/引文无效、来源/快照错配、必要安全条件、用户明确必须满足的软件/系统兼容、剩余核心缺证或冲突、无可用产品内容、必要图片不足。所有阻塞在 remaining_blockers 返回 code/reason/request_id/waivable。

新 FactRequest 可选字段：depends_on（请求 id 数组）、waivable（默认 true）、guardrail（none/identity/safety/compatibility，默认 none）。required 表示证据需求优先级，不自动表示不可舍弃。只有带明确关联的已舍弃冲突可隔离；无关联旧字符串冲突不自动吞掉，仍需补资料或重新描述。普通兼容性兴趣可舍弃，必要安全或明确必须满足的兼容门槛不能局部解除。

## 补充依据与真正刷新

任务级上传尚不支持。用户须在原云端 ima 知识库更新资料，或替换任务固定路径的本地 ZIP，然后调用：

~~~http
POST /api/tasks/{id}/refresh-evidence
Content-Type: application/json

{"version": 25}
~~~

返回同样 HTTP 202 accepted。状态：needs_review/brief_ready/plan_ready/approved → retrieving → planning → plan_ready 或 needs_review。保留原始确认、历史和 evidence_refreshes（原/新快照、资料指纹、用户请求版本、完成状态）。当前已授权舍弃不会因新资料到达而自动恢复；若要重新改变这些要求需明确重新描述。

此接口强制刷新云端目录缓存、读取新原文、重新提取原始完整 coverage，并重取图片。新图片按内容创建新缓存 ID，旧版本图片字节保留。更新后的本地 ZIP 接受新快照，不要求为相同已确认型号重新跑 Brief；若该型号已不存在则暂停，不改选其他产品。

原 confirm-brief 会先清除当前资料包再常规检索；ZIP 已变化时受旧快照校验限制，因此补资料应使用 refresh-evidence。resume-plan 只重新检查旧资料，不会自动读取更新后的包。刷新资料不等于审查通过，仍检查全部门槛。

## 验证边界

新增 37 项资料审查测试；完整后端 164 项通过。覆盖只读预览、依赖闭包、独立事实保留、显式确认与 409、防空内容、原始 hash/coverage 保留、非舍弃门槛、拒绝降级条件授权、冲突隔离、Planner/Writer/Reviewer/修订/手动编辑防回流、来源与快照刷新、保留旧图片字节、云端缓存刷新。

测试使用临时数据库、合成 ZIP、fixture 模型与 HTTP，不代表真实模型营销质量评分。本次不修改现有真实用户任务，不对其触发确认、舍弃或生成。


## 2026年10月18日 按钮与同方向取舍修复
- “调整内容，继续创作”在已选中该处理方式且有舍弃项时，打开只读取舍预览；未勾选时给出提示。确认授权与规划确认仍保留。
- 修复同方向级联误删：续航请求与型号核查同属一个方向时，舍弃续航不会删除已确认型号；手写笔请求依赖触屏请求，舍弃手写笔不会反向删除已有触屏依据。
- 区分手写笔支持与触屏能力，后续不得恢复已舍弃的手写笔用途。保留的部分方向采用当前请求生成中性说明。
- 真实暂停任务只读验证：f2/f5/f6 舍弃后保留 f1/f3/f4 和四条既有事实，无阻塞；未保存任务、未调用外部模型。用户需重新预览并显式确认。
