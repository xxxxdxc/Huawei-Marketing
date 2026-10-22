import type { Task } from './types';
import type { EvidenceTarget } from './Evidence';

export default function EvidenceCoverage({ task, onInspect }: { task: Task; onInspect: (target: EvidenceTarget) => void }) {
  const pkg = task.package;
  if (!pkg?.coverage?.length) return null;
  return <details className="notice"><summary>检索结果与内容取舍（{pkg.coverage.length} 项）</summary><p>保留原始检索结果。省略项不代表已找到依据，也不进入当前可用事实。</p>
    {pkg.coverage.map(item => {
      const scopeOmitted = task.execution_scope?.omitted_request_ids.includes(item.request_id);
      const gap = pkg.evidence_gaps?.find(g => g.request.id === item.request_id);
      const request = pkg.retrieval_plan?.facts.find(r => r.id === item.request_id) || gap?.request;
      const omitted = pkg.content_policy?.omitted_requests.find(r => r.request_id === item.request_id);
      const blocked = gap || pkg.content_policy?.blocked_requests?.find(r => r.request_id === item.request_id);
      const refs = gap?.blocking_evidence || omitted?.blocking_evidence || [];
      return <section className="coverage-item" key={item.request_id}><h3>{request?.question || `检索项 ${item.request_id}`}</h3>
        <p>检索结果：{{ supported: '有相关依据', partial: '部分有依据，可按已有事实使用', not_found: '未找到依据', conflict: '资料冲突', not_usable: '依据不可用' }[item.status] || item.status} · {scopeOmitted ? '用户已确认省略，原始结果保留' : blocked ? '待处理，尚不能继续' : omitted ? '本次省略此项' : '以当前可用事实为准'}</p>
        <p>{item.reason}</p>{item.missing_details?.length ? <p>尚未明确：{item.missing_details.join('；')}</p> : null}{item.usage_limits?.length ? <p>使用边界：{item.usage_limits.join('；')}</p> : null}{omitted && omitted.reason !== item.reason && <p>处置原因：{omitted.reason}</p>}
        {gap && !scopeOmitted && <p>暂停原因：{gap.blocking_reason === 'user_refuses_generation' ? '你曾明确要求缺少此项就不生成；请补充依据或修改该条件。' : gap.reason || '关键产品证据缺失或存在冲突，请处理后再继续。'}</p>}
        {refs.map((ref, i) => <blockquote key={i}>用户要求：{ref.quote}</blockquote>)}
        <div className="reference-links">{item.fact_ids.map(id => <button key={id} className="text-link" onClick={() => onInspect({ type: 'fact', id })}>查看依据 {id}{!pkg.facts.some(f => f.id === id) ? '（仅供追溯）' : ''}</button>)}</div>
      </section>;
    })}
  </details>;
}
