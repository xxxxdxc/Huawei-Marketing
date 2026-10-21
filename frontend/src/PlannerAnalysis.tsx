import { BookOpenCheck, ChevronRight, Layers3, ListOrdered } from 'lucide-react';
import type { Plan, Task } from './types';
import { Badge } from './shared';
import type { EvidenceTarget } from './Evidence';
import { POINT_GUIDANCE, executedPoints } from './plannerPresentation';

const SCORE_LABELS: Record<string, string> = { audience: '受众关联', evidence: '证据强度', differentiation: '本篇辨识度', image: '图片支持' };
type Props = { plan: Plan; task: Task; dirty: boolean; selectedIds: string[]; selectionChanged: boolean; editable: boolean; onSelectionChange: (ids: string[]) => void; onInspect: (target: EvidenceTarget) => void };
export default function PlannerAnalysis({ plan, task, dirty, selectedIds, selectionChanged, editable, onSelectionChange, onInspect }: Props) {
  const analysis = plan.planning_analysis;
  if (!analysis) return null;
  const candidates = [...(analysis.candidates || [])].sort((a, b) => a.rank - b.rank);
  const stale = dirty || analysis.status !== 'generated';
  const actualIds = new Set(executedPoints(plan));
  const platform = task.brief?.platform || task.platform;
  const selectionOnly = plan.schema_version === '3';
  return <section className="planner-analysis" aria-label="卖点取舍与排序">
    <div className="planner-panel-title"><span className="planner-symbol"><ListOrdered size={20} aria-hidden="true" /></span><div><h3>选出这篇要讲的重点</h3><p>{POINT_GUIDANCE[platform]}，也可按实际需求调整。不必把所有候选写进一篇内容。</p></div><Badge>{selectedIds.length} / {candidates.length} 已选</Badge></div>
    <p className="planner-score-disclaimer">评分帮助比较候选。推荐同时考虑任务要求、证据与内容重复程度，不直接按分数截取；评分不是产品性能或营销效果预测。</p>
    {stale && <p className="planner-stale" role="status">规划已修改，以下评分仅为生成时记录，不代表当前规划的最新评价。</p>}
    <div className="planner-point-list">{candidates.map(candidate => {
      const chosen = selectedIds.includes(candidate.id), actual = actualIds.has(candidate.id);
      return <article key={candidate.id} className={`planner-point ${chosen ? 'included' : ''}`}>
        <div className="planner-point-heading"><span className="planner-rank" aria-label={`排序第 ${candidate.rank}`}>{String(candidate.rank).padStart(2, '0')}</span><div><label className="planner-point-choice"><input type="checkbox" checked={chosen} disabled={!editable} aria-label={`选用卖点：${candidate.direction}`} onChange={e => onSelectionChange(e.target.checked ? [...selectedIds, candidate.id] : selectedIds.filter(id => id !== candidate.id))} /><span>{candidate.direction}</span></label><p>{candidate.audience_need}</p></div><span className="planner-point-state">{selectionOnly ? chosen ? selectionChanged ? '待提交选用' : '本篇选用' : '备选方向' : selectionChanged ? chosen ? '待更新采用' : actual ? '原大纲仍采用' : '备选方向' : actual ? '本篇采用' : '备选方向'}</span><span className="planner-score"><strong>{Number.isFinite(candidate.total_score) ? candidate.total_score.toFixed(1) : '—'}</strong><small>/ 100</small></span></div>
        <p className="planner-recommendation"><strong>{candidate.recommendation === 'recommended' ? '系统推荐' : candidate.recommendation === 'alternative' ? '保留备选' : '原规划记录'}</strong>{candidate.recommendation_reason || '这份历史规划未记录推荐理由，可结合原文和段落安排自行检查。'}</p>
        <div className="planner-point-evidence">{candidate.fact_ids.map(id => <button type="button" className="reference-chip" key={id} onClick={() => onInspect({ type: 'fact', id })}><BookOpenCheck size={13} aria-hidden="true" />{id} · 查看原文</button>)}{candidate.image_ids.map(id => <button type="button" key={id} className="text-link" onClick={() => onInspect({ type: 'image', id })}>查看关联图片<ChevronRight size={13} aria-hidden="true" /></button>)}</div>
        {!!candidate.conditions.length && <p className="planner-conditions"><strong>适用条件</strong>{candidate.conditions.join('；')}</p>}
        <details className="planner-score-detail"><summary>查看评分依据</summary><div>{Object.entries(candidate.scores).map(([key, score]) => <div className="planner-score-row" key={key}><span>{SCORE_LABELS[key] || key}</span><strong>{score.value}/4</strong><p>{score.reason}</p></div>)}</div></details>
        {actual && !selectionOnly && <p className="planner-linked-sections"><Layers3 size={13} aria-hidden="true" />当前大纲：{plan.sections.filter(s => s.point_ids?.includes(candidate.id)).map(s => s.heading || '未命名段落').join(' / ') || '尚未安排承接段落'}</p>}
      </article>;
    })}</div>
    {!candidates.length && <p className="muted">{selectionOnly ? '当前没有可用候选，请检查资料或重新获取卖点建议后再确认。' : '此规划没有可信候选记录。可检查原大纲；换选卖点前需要重新取得可用规划。'}</p>}
    <details className="planner-audit"><summary>查看生成时的卖点排序与依据</summary><p>受众关联 35% · 证据强度 35% · 本篇辨识度 15% · 图片支持 15%。总分由服务端按四项判断计算。</p><p>{selectionOnly ? '候选依据与编号经过程序检查。确认核心卖点后，系统才编排并写作；最终文稿仍需事实和图片核验。' : stale ? '原排序和评价仅供参考；保存后以服务端返回的规划为准。' : '生成时引用与结构经过程序检查，内容语义和实际图文匹配仍需你确认，并在成稿后核验。'}</p><p>当前产品：{task.package?.product.name}</p></details>
    {!!analysis.warnings?.length && <div className="planner-server-warnings"><strong>规划提示</strong><ul>{analysis.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></div>}
  </section>;
}
