# Brief V2 后端接口与前端接入

日期：2026-10-18。只改 backend/ 与 docs/；现有前端仍需接入自然语言入口和新版追问展示。

## 官方 Skill 的使用方式

保留 backend/vendor/campaign-plan/SKILL.md 原文、Apache 2.0 LICENSE 与 source.json（Git blob SHA、SHA-256）。没有创建或安装三个独立营销 Skill。
backend/brief_adapter.md 仅定义华为 PC 单篇图文的范围、事实边界和各阶段要求。brief_agent.py 运行时读取官方文件的适用章节，叠加项目适配规则，固定调用 Sonnet 三次：parsing → audience → strategy。缺项或冲突时只运行 parsing。
每次调用保留真实输入、输出、模型、时间、阶段状态及源文件/适配文件哈希，位于 task.brief_runs；它是调试记录，不是内部思维过程或质量评分。

## 入口与展示

POST /api/tasks 的 product_id、platform 现在可省略或 null：

```json
{"raw":"给大学新生写一篇图文，回应上课携带电脑的需求"}
```

返回 201 后，仍由前端 POST /api/tasks/{id}/analyze {version} 启动，202 后顺序轮询 GET task。仅传自然语言创建任务不要求 ima 在线；分析阶段只读产品目录，用户确认前不读取产品正文或图片。
选择器仍可作为快捷输入，两个字段继续接受原有值。一个任务只支持一个型号、一个平台，不新增跨型号选购推荐。

GET task 新增：

- brief_analysis：新版唯一权威 MarketingBrief；schema_version=2。
- brief_analysis_hash：当前分析内容哈希，由 GET 动态计算。
- brief_confirmation：用户确认的 analysis_hash、at、authorized_version；没有确认时 null。
- dialogue：原始输入、选择器和历次回答；每条有稳定 turn id。
- brief_runs：真实阶段调用记录；按实际状态展示，不推算百分比。

brief_analysis.requirements 包含 product_query、product_model、target_audience、scenario、buying_stage、customer_needs、marketing_goal、platform、user_constraints。每项包含 value/source/evidence/reason；evidence 指向 dialogue 的 turn_id 与逐字 quote。文本未知值 null，列表未知值 []。source 为 explicit、inferred、unknown。用户确认另行记录，不覆盖原始推断来源。

product_resolution 含 state、product_id、product_model、candidates（id/name/category）。初始模糊系列名可能匹配多个系统/配置，必须追问。明确的选择器或针对型号问题的明确回答可消除歧义；候选不是推荐或能力排序。

## 追问和冲突

外层 task.status 维持原枚举：needs_information 或 brief_ready 等。内层 brief_analysis.status：

- need_clarification：关键缺项。
- needs_resolution：条件冲突；最新明确修改通常替代旧要求，不仅因前后不同就报冲突。
- ready：完整需求、洞察、策略和检索计划已生成，等待用户确认；不代表已检索。

questions 含 id/field/kind/question/reason/choices。展示当前问题与可选回答；保留自由输入。提交：

```json
{"version":12,"answers":[{"question_id":"Q1","answer":"小红书"},{"question_id":"Q2","answer":"HUAWEI MateBook 14（鸿蒙电脑）"}]}
```

POST /api/tasks/{id}/brief/answers 返回 202，重新分析所有对话。可以只回答部分问题，剩余问题会重新计算。旧问题编号、重复编号、空回答被拒绝；过期 version 返回 409。回答字段是用户原文，后台不把模型自己的问题当作用户事实。

关键字段缺失时不生成完整策略；非关键缺项可以推断并标记。不得通过修改或清空 questions 继续。

## 策略与证据计划

ready 时包括 audience_insight（JTBD、问题、决策因素及理由）、message_strategy（主题、优先级、角度、CTA、语气）和 retrieval_plan（facts/images）。
所有卖点方向 verification=pending；事实请求关联 direction_id，写明问题、条件和 required/supporting；图片请求仅描述所需内容，不填不存在的图片 id，不提前安排段落。
确认后 ima 在指定型号目录读取原文，额外执行产品名及最多两项定向搜索，并记录 request_searches。搜索结果不会使其他型号文档混入指定目录。全部事实请求都参与原文提取与 coverage 判断，不限于执行过定向搜索的两项。
产品核心事实请求未被支持或产品事实冲突，进入 needs_review，package.evidence_gaps 给出原因，不继续选图与写作。价格/优惠缺失或冲突则省略并继续，详见下方 0.2.1 规则。用户补资料或 /modify 调整需求后重新确认。支持性请求缺失不会被虚构为已有事实。
图片方向参与候选排序与实际视觉筛选；Content Planner 仍在选图后确定段落、卖点顺序与配图。第二次人工确认保持不变。

## 用户确认与编辑兼容

推荐新版确认请求：

```json
{"version":22,"analysis_hash":"GET task 返回的 brief_analysis_hash"}
```

POST /api/tasks/{id}/confirm-brief 返回 202 后才会检索。后端验证 ready、问题已解决、型号唯一、平台确定和哈希/版本；直接调用内部 plan 也检查确认记录。

task.brief 保留旧版扁平结构作为只读兼容投影；平台尚未知时 brief=null，应以 brief_analysis 展示追问。旧客户端提交与投影完全相同的 {version,brief} 仍可确认。

若旧策略卡编辑了受众、语气等字段，再提交 confirm-brief，后端将修改记为用户反馈，启动 analyze 而非检索；完成后必须再次确认。直接清空或改变 questions 会拒绝。不能在前端把 202 统一解释为“已经开始检索”，应读取 status/events。

新版需求/策略修改可用现有 POST /modify {version,instruction}，回到 Brief 并使下游资料、规划、成稿、核验和旧确认失效。这不是定向修订接口。

旧历史任务不会被批量改写。旧流程的确认接口继续可用；重新分析/修改时进入 V2。历史恢复保留对应数据但清除确认和核验；V2 若要重新检索，必须再次确认。

## 前端接入范围

1. 创建页允许只输入自然语言，型号/平台选择器可选。
2. 策略页优先读取 brief_analysis，标明用户明确、模型推断、未知；区分需求、洞察、策略与待验证卖点。
3. 用新版 questions 和 answers 接口处理多轮补充；ready 后展示完整策略再确认。
4. 保存后轮询实际状态；无需改动 plan/document/review/export 的请求结构。
5. 完整模式下的 brief_runs 可作为调试详情，不应把模型阶段完成等同于资料已核验。

实际字段约束见 docs/openapi.json。现有精确问题定位、定向修订、带意见重规划仍未实现，不在本轮范围内。


## 0.2.1：通用 CTA 与价格优惠非阻塞策略

- “引导到店体验/咨询”可作为通用 CTA，没有门店、城市、体验安排不追问。只有用户明确要求文案写出具体地址、活动时间、预约安排且信息缺失时才追问。
- 解析阶段 commercial_requests 仅记录用户明确需要的 price/promotion 请求及原话证据。否定要求“不写价格优惠”不属于检索需求。未提及则不主动询问或添加任务。
- FactRequest 新增 category=product/price/promotion（旧记录默认 product）；重要性 priority 不再等价于是否必须阻塞。
- 用户明确要价格优惠时，确认 Brief 后检索 P1/08 官方公开价格快照，只匹配选定型号，保留原始 CSV 行、配置、核验时间、渠道/资格条件。P4 受控模板不能当实际政策。快照不自动等于今天门店成交价。
- 关键产品证据缺失/冲突仍阻塞；价格优惠未找到、不可用于当前要求或互相冲突，自动省略具体金额与政策，继续围绕已有产品事实进入 plan_ready。即使用户原先说“必须写价格”也不再次询问是否接受省略，明确记录该项未满足。
- 真实 coverage.status 保持 not_found/conflict，不伪造为 supported。V2 conflicts 改为结构化 category/request_ids/source_ids/detail，避免商业冲突掩盖产品冲突。
- package.content_policy 保存 omit_commercial、allowed_categories、omitted_requests、omitted_fact_ids、notices、approval_required=false。package.all_facts/all_conflicts 保留原始提取记录；package.facts/conflicts 是实际可用于生成和阻塞判断的结果。被省略的 coverage 引用可在 all_facts 追溯。
- 提示通过真实 events 和 content_policy.notices 展示给用户，不进入营销正文。Planner/Writer/Reviewer/修订都接收同一处置；自动省略不是核验失败，成稿恢复无依据金额或优惠仍会报错。
- 前端请求结构不变。可补充展示省略原因和未满足项；无需添加新的确认弹窗。后端没有改动 frontend/。


## 0.2.2：逐项保留、明确拒绝降级与旧任务恢复（覆盖 0.2.1 的整类省略规则）

1. 价格和优惠按 request_id 判断。价格有依据、教育优惠无依据时，只省略后者；同一类别也不能因一项失败删除其他独立、已支持的事实。存在冲突或不可用的事实不能被别的请求重新引入。
2. CommercialNeed 增加 on_missing=omit/block（默认 omit）和 blocking_evidence。只有用户明确说“没有/找不到该项就不生成、否则不出稿”等拒绝降级条件才可 block。仅“必须写优惠”、模型 priority=required 或模型自行填 block 均不能创建用户硬约束。后端核对真实 dialogue 原话；后续明确接受省略可解除条件。
3. 硬约束也不在 Brief 阶段因证据尚未知而追问/阻塞。先完成策略与用户确认，实际检索未支持指定项时进入 needs_review，并以 blocking_reason=user_refuses_generation 指明原因。普通缺证提示“未找到价格及优惠依据，本次不包含这些内容”，直接继续规划，不增加确认步骤。
4. content_policy 增加 requested_categories、omitted_categories、blocked_requests；allowed_categories 表示当前真正保留的商业事实类别。omit_commercial 只在没有保留商业事实时为 true。Reviewer 按省略类别与事实编号检查，不能因优惠省略而禁止已支持的价格。
5. 旧任务更新服务后不会自动回算持久化状态。新增 POST /api/tasks/{id}/resume-plan {version}：仅允许原 Brief 已确认、已有原文/事实/图片/coverage、尚无 plan/document 且处于 needs_review（或相应可重试错误）时调用。使用保存的原始资料重新判断并选图/规划，不重新检索或提取事实，不重写原确认记录；完成后停在 plan_ready，仍需用户确认规划才写稿。
6. 旧资料缺少 category/commercial_requests 时，按确认过的检索请求识别商业意图，保持默认省略。辅助请求只引用了被省略的政策说明时，不将其误报为核心产品缺证。核心产品事实冲突仍暂停。
7. GET task 不再给旧 canonical Brief 注入新默认字段，避免返回内容与 brief_analysis_hash 不一致。前端仍应使用服务端返回的 version/hash。
8. 前端可对“needs_review + 有 package.coverage + 无 plan/document”的任务展示“按当前规则继续规划”，调用 resume-plan；不需要用户重新填写整个需求。接口不等于通用重规划或定向修订，既有规划/成稿不允许被此接口覆盖。


## 0.5.0 资料审查局部取舍与重查

接口与完整请求/响应示例见 [EVIDENCE_RESOLUTION.md](EVIDENCE_RESOLUTION.md)。新增 GET /api/tasks/{id}/evidence-review、POST /evidence-resolution/preview、POST /evidence-resolution/confirm、POST /refresh-evidence（后3项均在 /api/tasks/{id} 下）。预览只读；确认需 version、preview_id、confirmed=true 及受影响约束的明确授权。复用资料后停 plan_ready，不自动写稿。原始 Brief/确认哈希/coverage 保留；execution_scope 和 resolution_history 单独记录。取舍边界贯穿规划、写稿、核验、修订与手动编辑后的核验。任务级上传未实现，补入原 ima 或替换固定路径 ZIP 后使用 refresh-evidence；该入口实际重取资料并接受新 ZIP 快照。/modify 整体变更仍失效当前各阶段产物；/replan 与 /resume-plan 不作为任意降级接口。FactRequest 新增可选 depends_on、waivable、guardrail，不改写历史已确认 Brief。
