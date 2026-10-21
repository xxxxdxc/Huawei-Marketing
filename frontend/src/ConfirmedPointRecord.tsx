import type { Task } from './types';
import { Badge } from './shared';
import { confirmedPlatformPlan, platformChangeContext } from './platformPresentation';

export default function ConfirmedPointRecord({ task }: { task: Task }) {
  const plan = confirmedPlatformPlan(task);
  const snapshot = platformChangeContext(task);
  if (!plan || !snapshot) return null;
  const candidates = plan.planning_analysis?.candidates || [];
  return <section className="confirmed-point-record" aria-label="原确认卖点记录">
    <div className="section-heading"><div><h2>已确认的核心卖点</h2><p>本次只调整发布平台，以下选用记录保留，无需再次确认。</p></div><Badge>已确认 · 保留</Badge></div>
    <ol>{plan.selected_point_ids!.map(id => {
      const candidate = candidates.find(item => item.id === id);
      const facts = (snapshot.facts || []).filter(fact => candidate?.fact_ids.includes(fact.id));
      return <li key={id}><strong>{candidate?.direction || `卖点 ${id}（原记录未提供说明）`}</strong>{candidate?.audience_need && <p>{candidate.audience_need}</p>}
        {!!facts.length && <details><summary>查看原确认依据</summary><p className="muted">以下为确认时保存的证据，不代表新平台稿件已核验。</p>{facts.map(fact => <div className="confirmed-point-evidence" key={fact.id}><p><strong>{fact.id} · {fact.claim}</strong></p><blockquote>{fact.quote}</blockquote><p>来源：{fact.source_id}</p>{fact.conditions && <p>适用条件：{fact.conditions}</p>}</div>)}</details>}
      </li>;
    })}</ol>
  </section>;
}
