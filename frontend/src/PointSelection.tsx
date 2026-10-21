import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, Save } from 'lucide-react';
import type { Task } from './types';
import { Badge, BUSY, effectiveStatus, type Act } from './shared';
import { executedPoints, samePointSelection } from './plannerPresentation';
import type { EvidenceTarget } from './Evidence';
import PlannerAnalysis from './PlannerAnalysis';

type Props = { task: Task; locked: boolean; act: Act; onDirty: (dirty: boolean) => void; onInspect: (target: EvidenceTarget) => void };
export default function PointSelection({ task, locked, act, onDirty, onInspect }: Props) {
  const plan = task.plan!;
  const [selectedIds, setSelectedIds] = useState(() => executedPoints(plan));
  const serverVersion = useRef(task.version);
  const changed = !samePointSelection(selectedIds, executedPoints(plan));
  const retryable = task.status === 'error' && effectiveStatus(task) === 'plan_ready' && !!task.selection_confirmation;
  const canConfirm = plan.phase === 'selection' || retryable;
  const editable = !locked && canConfirm && effectiveStatus(task) === 'plan_ready';
  useEffect(() => {
    if (serverVersion.current === task.version) return;
    serverVersion.current = task.version;
    if (BUSY.includes(task.status) || task.error) return;
    setSelectedIds(executedPoints(task.plan));
  }, [task.version, task.plan, task.status, task.error]);
  useEffect(() => { onDirty(changed); }, [changed, onDirty]);
  const candidates = plan.planning_analysis?.candidates || [];
  const invalid = selectedIds.length === 0 || selectedIds.length > 8 || selectedIds.some(id => !candidates.some(candidate => candidate.id === id));
  return <>
    <div className="section-heading"><div><p className="overline">第二次确认 · 核心卖点</p><h2>{canConfirm ? '先确定这篇要讲什么' : '本篇采用的核心卖点'}</h2><p>{canConfirm ? '选好重点后，系统会自动安排结构、图片并完成正文，不再额外确认大纲。' : '这些卖点是写作依据。结构编排由写作环节完成，最终文稿仍需核验。'}</p></div><Badge>{canConfirm ? '待确认卖点' : '选用记录'}</Badge></div>
    <div className="plan-context"><span>营销目标</span><strong>{task.brief?.goal}</strong></div>
    <div className="planner-route" aria-label="核心卖点到成稿的流程"><span>候选与证据</span><ArrowRight size={14} aria-hidden="true" /><span>你确认核心卖点</span><ArrowRight size={14} aria-hidden="true" /><span>自动编排并写作</span><ArrowRight size={14} aria-hidden="true" /><span>核验与编辑</span></div>
    <PlannerAnalysis plan={plan} task={task} dirty={false} selectedIds={selectedIds} selectionChanged={changed} editable={editable} onSelectionChange={setSelectedIds} onInspect={onInspect} />
    {canConfirm && <>
      <div className="planner-selection-actions" aria-live="polite"><div><strong>{changed ? `已调整为 ${selectedIds.length} 个卖点，确认时一并提交` : `已保存 ${selectedIds.length} 个卖点`}</strong><p>保存只记录选择，写作会在确认后开始。也可直接确认，一并提交当前选择。</p>{invalid && <p className="budget-warning">请先选用 1–8 个候选卖点。</p>}</div><div className="planner-selection-buttons">{changed && <button className="secondary" disabled={!editable} onClick={() => setSelectedIds(executedPoints(plan))}>撤销选用调整</button>}<button className="secondary" disabled={!editable || !changed || invalid} onClick={() => act('/replan-points', { version: task.version, selected_point_ids: selectedIds, replace_current_plan: true })}><Save size={16} aria-hidden="true" />保存卖点选择</button></div></div>
      <div className="planner-next-step"><CheckCircle2 size={19} aria-hidden="true" /><div><strong>确认后，自动完成结构与正文</strong><p>系统会围绕已选卖点安排主线、段落和配图，再生成适合当前平台的图文。你可在生成后编辑，并重新核验。</p></div></div>
      <div className="action-bar planner-confirm-bar"><span className="planner-confirm-hint">{locked ? '正在处理…' : changed ? '确认时会提交当前选择，并开始编排与写作。' : '这是开始写稿前的第二次人工确认。'}</span><button className="primary" disabled={!editable || invalid || !!task.package?.conflicts.length} onClick={() => act('/confirm-plan', { version: task.version, plan: { ...plan, selected_point_ids: selectedIds } })}>{retryable && !changed ? '重试编排并写稿' : '确认卖点，开始写稿'}<ArrowRight size={16} aria-hidden="true" /></button></div>
    </>}
  </>;
}
