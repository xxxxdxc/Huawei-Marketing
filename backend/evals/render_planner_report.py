"""Render public, aggregate-only evaluation report after all 15 pairs finish."""
import collections,json,sys
from pathlib import Path

def main():
 root=Path(sys.argv[1]);data=json.loads((root/'summary.json').read_text(encoding='utf-8'));manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));s=data['summary'];rows=data['rows'];before=s['before'];after=s['after']
 def f(n):return f'{n:.2f}'
 lines=['# Content Planner V2 首轮真实评测','', '日期：2026-10-21。此报告只覆盖 Planner；不代表完整智能体线上端到端测试，也不是投放效果或人工用户研究。','', '## 方法与样本','', '固定15例，5种受众/购买需求 × 3个平台；使用3个型号的同一组真实ima快照（24张事实卡、13张经核验图片）。每例旧版、新版各跑一次，按固定种子交错执行，最大并发2对。旧版为冻结的一阶段规划，新版为候选生成、程序排序、叙事段落规划两阶段。请求与返回模型标识均为claude-sonnet-5-5；独立盲评请求与返回标识为gpt-6.1-sol。网关标识不等同独立核实底层模型身份。','', 'GPT对匿名A/B按相同0–4量表评价，不看版本和候选自评分。比较共有的角度、段落目的、事实与图片关联，不因V2增加字段而自动加分；新增布局/元数据完整度由程序和浏览器测试单独验证。每个案例只有一次采样，不能据此声称统计显著或稳定优于基线。','', '## 汇总','', '| 指标 | 旧版 | V2 | 变化（V2−旧版） |','| --- | ---: | ---: | ---: |']
 for key,label in [('selling_points','卖点选择（0–4）'),('narrative','叙事质量（0–4）'),('evidence_fidelity','证据语义忠实度（0–4）'),('image_relation','图文关联（0–4）')]:
  a=before['grades'][key];b=after['grades'][key];lines.append(f'| {label} | {f(a)} | {f(b)} | {b-a:+.2f} |')
 for key,label in [('median_seconds','方案耗时中位数（秒）'),('mean_seconds','方案平均耗时（秒）')]:
  a=before[key];b=after[key];lines.append(f'| {label} | {f(a)} | {f(b)} | {b-a:+.2f} |')
 for key,label in [('success','成功返回完整方案'),('common_hard_valid','共有硬校验通过')]:lines.append(f"| {label} | {before[key]}/15 | {after[key]}/15 | {after[key]-before[key]:+d} |")
 for key,label in [('fact','事实ID'),('image','图片ID')]:
  a=f"{before['valid_'+key+'_refs']}/{before[key+'_refs']}";b=f"{after['valid_'+key+'_refs']}/{after[key+'_refs']}";lines.append(f'| {label}引用存在 | {a} | {b} | — |')
 lines+=['', 'ID存在率不证明内容语义真实，也不证明图片能证明参数；语义忠实度另由独立模型判断。失败仍计入15例分母。耗时包含该方案实际调用及结构重试，新版包含两阶段，不能用单次调用耗时掩盖总成本。','', '## 逐例结果','', '| 案例 | 平台 | 旧/新卖点分 | 旧/新叙事分 | 旧/新图文分 | 旧/新耗时秒 | 新叙事框架 |','| --- | --- | ---: | ---: | ---: | ---: | --- |']
 for c in manifest['cases']:
  a=next(r for r in rows if r['case']==c['id'] and r['version']=='before');b=next(r for r in rows if r['case']==c['id'] and r['version']=='after');lines.append(f"| {c['id']} | {c['platform']} | {a['grade']['selling_points']}/{b['grade']['selling_points']} | {a['grade']['narrative']}/{b['grade']['narrative']} | {a['grade']['image_relation']}/{b['grade']['image_relation']} | {f(a['seconds'])}/{f(b['seconds'])} | {b['framework'] or '失败'} |")
 lines+=['', '## 固定案例输入', '', '| 案例 | 型号 | 受众 | 购买阶段 | 场景 |', '| --- | --- | --- | --- | --- |']
 for case in manifest['cases']:
  product=manifest['material_hashes'][case['product_index']]['product'];brief=case['brief']
  lines.append(f"| {case['id']} | {product['name']}（{product.get('category','')}） | {brief['audience']} | {brief['purchase_stage']} | {brief['scenario']} |")
 frameworks=collections.Counter(r['framework'] for r in rows if r['version']=='after' and r['framework'])
 preferences=collections.Counter()
 critiques=[]
 for c in manifest['cases']:
  cid=c['id'];j=json.loads((root/f'{cid}_judge.json').read_text(encoding='utf-8'))['result'];pref=j['preference'];preferences[manifest['blind_assignment'][cid][0 if pref=='A' else 1] if pref in ('A','B') else 'tie']+=1
  newlabel='A' if manifest['blind_assignment'][cid][0]=='after' else 'B'
  if j[newlabel]['selling_points']<3 or j[newlabel]['image_relation']<3:critiques.append((cid,j[newlabel]['reasons']))
 lines+=['', 'V2框架分布：'+ '；'.join(f'{k} {v}例' for k,v in frameworks.items())+'。', '', '盲评偏好：'+ '；'.join(f'{k} {v}例' for k,v in preferences.items())+'。', '', '## 调用与费用证据','', f"主评测：旧版实际HTTP调用{before['http_calls']}次，新版{after['http_calls']}次，独立盲评"+str(sum(len(json.loads(p.read_text(encoding='utf-8'))['calls']) for p in root.glob('*_judge.json')))+'次。', '', f"网关返回的总token字段：旧版{before['total_tokens']}，新版{after['total_tokens']}（只统计有返回usage的调用）。不按未知费率估算人民币。原始逐调用elapsed_seconds、usage、response_model在私有结果中保存。", '', '资料准备另外产生9次有用量/状态审计的调用（含1次HTTP524），以及最早1次因原文摘录不匹配而废弃的提取调用；该次token审计未保留，不能把上述记录声称为全部费用。准备阶段改为原文片段编号选择并缩小视觉批次，事实与图片通过检查后才冻结评测材料。这些额外准备调用没有计入旧/新版方案时延。', '', '## 失败与不足','']
 failures=[r for r in rows if r['error'] or not r['metrics']['hard_valid']]
 if failures:
  lines += [f"- {r['case']} {r['version']}：{r['error'] or r['metrics']['error']}" for r in failures]
 else:lines+=['本轮全部方案完整返回且通过共有硬校验；仍不能把一次无错误推广为所有任务无错误。']
 if critiques:
  lines+=['', 'V2低分案例的独立盲评原始反馈（未据此改写本轮结果）：']
  lines += ['\n'+cid+'：'+'；'.join(reasons) for cid,reasons in critiques]
 lines+=['', '## 验证与复现','', '本地兼容性：232项完整后端回归（其中30项Planner专项测试）、64项浏览器测试、最后UI提示调整后的7项专项复验、TypeScript与生产构建通过。新增用例覆盖引用、型号、证据、重复问题、图片数量/位置/顺序、旧格式编辑、伪造评分与布局导出；测试使用隔离夹具，不冒充真实产品评测。真实模型证据仅指本报告15例Planner对比和独立盲评。', '', '原始材料与逐例结果位于 `.local/planner_evals/materials/ima_fresh_20261021_055235` 和 `.local/planner_evals/runs/20261021_v2`，均未纳入Git。公共代码包含固定案例、基线、方法来源与运行脚本；复现需本机合法凭证和相同资料快照。详见 [CONTENT_PLANNER_V2.md](CONTENT_PLANNER_V2.md)。','']
 lines.insert(12,'本轮图文关联、证据忠实度和硬校验通过率有所改善；叙事均分小幅提高，卖点选择均分下降，完整方案耗时明显增加。盲评偏好为新版8例、旧版6例、平局1例。本轮尚不能证明整体质量稳定优于旧版。下一轮优先检验需求覆盖、重复CTA和过多规格的问题；调整提示后需另建版本评测，不覆盖本轮记录。\n')
 Path('docs/CONTENT_PLANNER_EVAL.md').write_text('\n'.join(lines),encoding='utf-8')
if __name__=='__main__':main()
