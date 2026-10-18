import { useState } from 'react';
import type { Task } from './types';
import { EvidenceDialog, type EvidenceTarget } from './Evidence';

export function directionResults(task: Task, directionId: string) {
  const requests = (task.package?.retrieval_plan?.facts || task.brief_analysis?.retrieval_plan?.facts || []).filter(r => r.direction_id === directionId);
  const rows = requests.map(request => {
    const coverage = (task.package?.execution_coverage || task.package?.coverage)?.find(c => c.request_id === request.id);
    const scopeOmitted = task.execution_scope?.omitted_request_ids.includes(request.id);
    const omitted = task.package?.content_policy?.omitted_requests.find(r => r.request_id === request.id);
    const gap = scopeOmitted ? undefined : task.package?.evidence_gaps?.find(g => g.request.id === request.id);
    const blocked = scopeOmitted ? undefined : gap || task.package?.content_policy?.blocked_requests?.find(r => r.request_id === request.id);
    const conflict = coverage?.status === 'conflict' || omitted?.status === 'conflict';
    const supported = !scopeOmitted && coverage?.status === 'supported' && !omitted && !blocked && coverage.fact_ids.length > 0 && coverage.fact_ids.every(id => task.package?.facts.some(f => f.id === id));
    const label = scopeOmitted ? '用户已确认省略' : blocked ? (conflict ? '资料冲突 · 待处理' : '缺少依据 · 待处理') : omitted ? (conflict ? '资料冲突 · 本次省略' : '本次省略') : conflict ? '资料冲突' : supported ? '有相关依据' : coverage?.status === 'not_found' ? '未找到依据' : coverage ? '依据不足' : task.status === 'retrieving' ? '验证中' : '待验证';
    return { request, coverage, scopeOmitted, omitted, gap, blocked, conflict, supported, label };
  });
  const total = rows.length, found = rows.filter(r => r.supported).length;
  const label = !total ? '待关联检索项' : rows.some(r => r.blocked) ? '待处理' : rows.some(r => r.conflict && !r.scopeOmitted) ? '存在资料冲突' : rows.every(r => r.omitted || r.scopeOmitted) ? '本次省略' : found === total ? '有相关依据' : found > 0 ? '部分有依据' : rows.some(r => !r.coverage) ? (task.status === 'retrieving' ? '验证中' : '待验证') : rows.every(r => r.coverage?.status === 'not_found') ? '未找到依据' : '依据不足';
  return { rows, label, found, total };
}

export default function StrategyDirections({ task }: { task: Task }) {
  const [target, setTarget] = useState<EvidenceTarget | null>(null);
  const strategy = task.brief_analysis?.message_strategy;
  if (!strategy) return null;
  return <section className="strategy-proposal"><h3>内容方向与验证结果</h3><p className="muted">以下是要核实的问题，不是已经成立的产品结论。标签反映当前检索依据；最终表述仍须保留适用条件，并通过成稿核验。</p>
    <ul className="direction-list">{strategy.priorities.map((direction, index) => {
      const result = directionResults(task, direction.id);
      return <li key={direction.id} className="direction-item"><div className="direction-heading"><strong>验证方向 {index + 1}</strong><span className="pending-label" role="status">{result.label}</span></div>
        {!result.total && <p>当前记录缺少关联检索项，无法判断此方向的验证结果。</p>}
        {result.rows.map(row => <div className="direction-question" key={row.request.id}><h4>{row.request.question}</h4><p><span className="pending-label">{row.label}</span>{row.coverage?.reason || '确认策略后，将从知识库寻找相关依据。'}</p>{row.omitted && <p>内容取舍：{row.omitted.reason}</p>}{row.gap && <p>处理原因：{row.gap.reason || (row.gap.blocking_reason === 'user_refuses_generation' ? '你明确要求缺少此项就不生成，需补充依据或调整要求。' : '关键证据尚未满足，请查看知识库依据。')}</p>}
          {row.coverage?.fact_ids.map(id => <button className="text-link" key={id} onClick={() => setTarget({ type: 'fact', id })}>查看依据 {id}{!task.package?.facts.some(f => f.id === id) ? '（仅供追溯）' : ''}</button>)}
        </div>)}
        <details className="direction-original"><summary>查看原策略建议（非已核实结论）</summary><p>{direction.direction}</p><p>{direction.reason}</p></details>
      </li>;
    })}</ul>
    <details className="brief-details"><summary>查看原主题与切入角度（策略草案）</summary><p>{strategy.theme}</p><p>{strategy.angle}</p></details>
    <p>表达语气：{strategy.tone}</p><p>行动引导：{strategy.cta_direction}</p>
    {target && <EvidenceDialog task={task} target={target} onClose={() => setTarget(null)} />}
  </section>;
}
