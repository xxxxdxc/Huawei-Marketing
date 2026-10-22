import ManualEvidenceForm from './ManualEvidenceForm';
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, FileSearch, LoaderCircle, RefreshCw } from 'lucide-react';
import type { Task } from './types';
import type { ResolutionPreview, ReviewOverview } from './evidenceResolutionTypes';
import type { EvidenceTarget } from './Evidence';
import { api, ApiError, canResumePlan, effectiveStatus, errorMessage, Field, type Act } from './shared';

type Props = {task:Task;locked:boolean;act:Act;onDirty:(value:boolean)=>void;onInspect:(target:EvidenceTarget)=>void;onReload:()=>void};
export default function EvidenceResolution({ task, locked, act, onDirty, onInspect, onReload }: Props) {
  const [overview,setOverview] = useState<ReviewOverview|null>(null), [error,setError] = useState(''), [stale,setStale] = useState(false);
  const [loading,setLoading] = useState(true), [working,setWorking] = useState(false), [retry,setRetry] = useState(0);
  const [selected,setSelected] = useState<string[]>([]), [preview,setPreview] = useState<ResolutionPreview|null>(null), [acks,setAcks] = useState<string[]>([]);
  const [mode,setMode] = useState<'adjust'|'refresh'|'modify'>('adjust'), [updated,setUpdated] = useState(false), [instruction,setInstruction] = useState(''), [modifyConfirmed,setModifyConfirmed] = useState(false);
  const [supplementMode,setSupplementMode]=useState<'source'|'manual'>('source'),[manualDirty,setManualDirty]=useState(false);
  const alive = useRef(true), requestLock = useRef(false), previewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setOverview(null);
    api<ReviewOverview>(`/tasks/${encodeURIComponent(task.id)}/evidence-review`, 'GET', undefined, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      if (data.version !== task.version) { setStale(true); setError('任务已更新，请载入最新版本后再处理。'); return; }
      setOverview(data);
    }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [task.id,task.version,retry]);
  useEffect(() => { onDirty(Boolean(selected.length || instruction.trim() || updated || manualDirty)); }, [selected,instruction,updated,manualDirty,onDirty]);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  const disabled = locked || working || loading || stale;
  const canAdjust = ['needs_review','plan_ready'].includes(effectiveStatus(task)) && !task.document;
  const blockers = overview?.blockers || [];
  const unmet = overview?.unmet_requirements.filter(u => !u.omitted) || [];
  const readyToResume = Boolean(overview && canResumePlan(task) && !blockers.length && !unmet.length && overview.available_facts.length);
  function choose(id:string) { setSelected(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids,id]); setPreview(null); setAcks([]); setError(''); }
  function changeMode(next:typeof mode) { if (next === mode) return; if ((instruction.trim() || selected.length || updated) && !window.confirm('切换处理方式会清除尚未提交的选择和输入，继续？')) return; setMode(next); setPreview(null); setAcks([]); setSelected([]); setInstruction(''); setUpdated(false); setModifyConfirmed(false); setError(''); }
  function activateMode(next:typeof mode) {
    if (disabled) return;
    if (next === 'adjust' && readyToResume) { changeMode(next); return; }
    if (next !== 'adjust' || mode !== 'adjust') { changeMode(next); return; }
    if (!canAdjust) { setError('当前任务不能局部调整，请先返回可继续的步骤。'); return; }
    if (!selected.length) { setError('请先勾选本次不写的内容，再查看取舍影响。'); return; }
    if (preview) { previewHeading.current?.focus(); return; }
    void getPreview();
  }
  async function getPreview() {
    if (requestLock.current || disabled || !selected.length) return;
    requestLock.current = true; setWorking(true); setPreview(null); setAcks([]); setError('');
    try {
      const result = await api<ResolutionPreview>(`/tasks/${encodeURIComponent(task.id)}/evidence-resolution/preview`,'POST',{version:task.version,drop_request_ids:selected,drop_direction_ids:[]});
      if (!alive.current) return;
      if (result.version !== task.version || result.task_id !== task.id) throw new ApiError('预览与当前任务版本不一致，请重新载入。',409);
      setPreview(result);
    } catch(e) { if (alive.current) {setError(errorMessage(e)); if (e instanceof ApiError && e.status === 409) setStale(true);} }
    finally { requestLock.current = false; if (alive.current) setWorking(false); }
  }
  async function perform(path:string,body:unknown) {
    if (requestLock.current || disabled) return;
    requestLock.current = true; setWorking(true); setError('');
    try { const ok = await act(path,body); if (!ok && alive.current) { setPreview(null); setAcks([]); setError('操作未完成，选择和输入已保留。请处理页面提示后重新预览或重试。'); } }
    finally { requestLock.current = false; if (alive.current) setWorking(false); }
  }
  const directionName = (id:string) => task.brief_analysis?.message_strategy?.priorities.find(d => d.id === id)?.direction || id;
  const factName = (id:string) => overview?.available_facts.find(f => f.id === id)?.claim || task.package?.all_facts?.find(f => f.id === id)?.claim || task.package?.facts.find(f => f.id === id)?.claim || id;
  if (loading) return <div className="notice" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" /> 正在整理未满足的需求与可用处理方式…</div>;
  return <section className="evidence-resolution" aria-label="资料检查结果与下一步">
    <header className="resolution-heading"><span className="resolution-symbol"><FileSearch size={23} aria-hidden="true" /></span><div><h2>{readyToResume ? '资料缺口已处理，可以重新生成卖点建议' : blockers.length ? '先处理这些缺口，再继续规划' : unmet.length ? '部分需求尚无依据，可以调整内容' : '资料检查结果与下一步'}</h2><p>{readyToResume ? '当前没有未处理的资料门槛；卖点建议尚未生成成功，已有资料与取舍记录均已保留。' : blockers.length ? `${blockers.length} 项门槛尚未满足。已找到的资料会保留，请选择下方的处理方式。` : '检索结果与内容取舍分开记录；找到依据不等于成稿已核验。'}</p></div></header>
    {error && <div className="notice warning" role="alert"><p>{error}</p>{stale ? <button className="text-link" onClick={onReload}>重新载入最新版本</button> : !overview ? <button className="text-link" disabled={locked} onClick={() => setRetry(v=>v+1)}>重新读取审查结果</button> : null}</div>}
    {overview && <>
      {mode==='adjust' && readyToResume && <section className="resolution-preview planning-recovery" aria-label="恢复卖点规划"><h3>接下来：重新生成卖点建议</h3><p>当前尚未生成可确认的卖点建议。可以复用当前资料，重新检查并生成建议。</p><p>已确认的省略内容会保留，不会重新写入。</p><p>本次只恢复规划；如再次发现资料门槛会暂停，成功后仍需你确认核心卖点，才会开始写稿。</p><button className="primary" disabled={disabled} onClick={()=>perform('/resume-plan',{version:task.version})}><RefreshCw size={16} aria-hidden="true" />{working ? '正在提交…' : '重新生成卖点建议'}</button></section>}
      {blockers.length > 0 && <div className="resolution-blockers" role="status"><strong>为什么暂停</strong><ul>{blockers.map((b,i)=><li key={`${b.code}-${i}`}>{b.reason}{!b.waivable && <span className="pending-label">不能直接跳过</span>}</li>)}</ul></div>}
      {!readyToResume && <h3>尚未满足的需求</h3>}
      {!unmet.length && !readyToResume && <p className="muted">{readyToResume ? '无需再次勾选已省略的内容。请使用下方的恢复操作。' : '当前没有可调整的缺证项，请按上方门槛补充依据或重新描述需求。'}</p>}
      {unmet.map(u=><article className="unmet-card" key={u.request.id}><h4>{u.request.question}</h4><dl><dt>已找到</dt><dd>{u.found.length ? u.found.map(f=><button className="text-link" key={f.id} onClick={()=>onInspect({type:'fact',id:f.id})}>{f.claim}</button>) : '这项需求尚无可引用的直接依据；其他已找到的产品资料保留在下方。'}</dd><dt>仍缺少</dt><dd>{u.missing}</dd><dt>影响内容</dt><dd>{u.affected_direction_ids.map(directionName).join('；') || '此项相关表述暂不能写入文案'}</dd></dl>{mode === 'adjust' && <label className="resolution-check"><input type="checkbox" checked={selected.includes(u.request.id)} disabled={disabled || !canAdjust || !u.can_drop || !overview.actions.includes('adjust_content')} onChange={()=>choose(u.request.id)} /><span>本次不写这项内容{!u.can_drop && <small>{u.non_waivable_reason || '此项不能局部舍弃，请补充依据或重新描述需求。'}</small>}</span></label>}</article>)}
      {overview.unmet_requirements.some(u=>u.omitted) && <details className="brief-details"><summary>查看已省略但未满足的需求</summary><ul>{overview.unmet_requirements.filter(u=>u.omitted).map(u=><li key={u.request.id}>{u.request.question}：{u.missing}（已省略，不代表有依据）</li>)}</ul></details>}
      <div className="resolution-paths" aria-label="处理方式">
        {[['adjust',readyToResume ? '返回继续规划' : '调整内容，继续创作'],['refresh','补充依据，再检查'],['modify','重新描述需求']].filter(([id])=>id!=='adjust'||(readyToResume ? mode!=='adjust' : unmet.length>0)).map(([id,label])=><button key={id} className={mode===id?'primary':'secondary'} aria-pressed={mode===id} disabled={disabled} onClick={()=>activateMode(id as typeof mode)}>{label}</button>)}
      </div>

      {mode==='adjust' && unmet.length>0 && <div className="resolution-action"><p>勾选本次不写的内容，先查看关联影响，再决定是否继续。原始证据和历史版本会保留。</p><button className="primary" disabled={disabled || !canAdjust || !selected.length} onClick={getPreview}>{working ? '正在获取预览…' : '查看取舍影响'}<ArrowRight size={16} aria-hidden="true" /></button></div>}
      {preview && mode==='adjust' && <section className="resolution-preview"><h3 ref={previewHeading} tabIndex={-1}>确认本次内容调整</h3><h4>不再表达</h4><ul>{preview.removed.map(r=><li key={r.request.id}>{r.request.question}{!preview.selected_request_ids.includes(r.request.id) && <span className="pending-label">关联影响</span>}</li>)}</ul>
        {preview.affected_directions.length > 0 && <><h4>受影响的方向</h4><ul>{preview.affected_directions.map(d=><li key={d.direction.id}>{d.direction.direction}<p className="muted">{d.reason}</p></li>)}</ul></>}
        <h4>仍然保留</h4><ul>{preview.retained.map(r=><li key={r.request.id}>{r.request.question}</li>)}</ul>{!preview.retained.length && <p>没有剩余内容方向，不能继续生成。</p>}
        <details><summary>查看保留的事实及排除的素材</summary><ul>{preview.retained_fact_ids.map(id=><li key={id}>{factName(id)}</li>)}</ul>{preview.excluded_fact_ids.length>0 && <p>排除事实：{preview.excluded_fact_ids.map(factName).join('；')}</p>}{preview.excluded_image_ids.length>0 && <p>排除图片：{preview.excluded_image_ids.map(id=>task.package?.images.find(i=>i.id===id)?.name || id).join('、')}</p>}</details>
        {preview.prohibited_topic_labels.length>0 && <p>后续文稿不再包含：{preview.prohibited_topic_labels.join('、')}。</p>}
        {preview.remaining_blockers.length>0 && <div className="notice warning"><strong>调整后仍需处理</strong><ul>{preview.remaining_blockers.map((b,i)=><li key={i}>{b.reason}</li>)}</ul><p>请补充相应依据，或返回修改选择。当前不能继续规划。</p></div>}
        {preview.required_constraint_acks.map(c=><div className="constraint-ack" key={c.id}>{c.evidence.map((e,i)=><blockquote key={i}>你原来的要求：“{e.quote}”</blockquote>)}{c.requires_ack ? <label className="resolution-check"><input type="checkbox" disabled={disabled} checked={acks.includes(c.id)} onChange={e=>setAcks(a=>e.target.checked?[...a,c.id]:a.filter(id=>id!==c.id))}/><span>我同意本次放宽此要求：{c.description}</span></label> : <p>此条件已获得本次执行范围的授权。</p>}</div>)}
        <p>{preview.requires_asset_review ? '部分素材仍需核验；' : ''}确认后复用合格资料重新规划。如仍有缺口会暂停；规划完成后，仍由你确认才开始写稿。</p>
        <div className="resolution-buttons"><button className="primary" disabled={disabled || !preview.can_apply || preview.remaining_blockers.length>0 || preview.required_constraint_acks.some(c=>c.requires_ack&&!acks.includes(c.id))} onClick={()=>perform('/evidence-resolution/confirm',{version:preview.version,preview_id:preview.preview_id,drop_request_ids:preview.selected_request_ids,drop_direction_ids:preview.selected_direction_ids,confirmed:true,acknowledged_constraint_ids:acks})}>确认调整，继续规划</button><button className="secondary" disabled={disabled} onClick={()=>{setPreview(null);setAcks([]);}}>取消确认</button></div>
      </section>}
      {mode==='refresh' && <section className="resolution-preview"><h3>补充资料后，重新检查</h3>
        <div className="resolution-buttons" role="group" aria-label="补充依据方式"><button className={supplementMode==='source'?'primary':'secondary'} disabled={disabled} aria-pressed={supplementMode==='source'} onClick={()=>setSupplementMode('source')}>更新原资料源</button><button className={supplementMode==='manual'?'primary':'secondary'} disabled={disabled} aria-pressed={supplementMode==='manual'} onClick={()=>setSupplementMode('manual')}>手动补充原文</button></div>
        {supplementMode==='source' ? <><p>当前资料源：<strong>{overview.knowledge_source==='local_zip'?'本地 ZIP 资料包':overview.knowledge_source==='ima'?'ima 知识库':overview.knowledge_source}</strong></p>{overview.local_archive_path && <p className="source-path">更新位置：{overview.local_archive_path}</p>}<p>{overview.knowledge_source==='local_zip'?'请在原固定路径替换更新后的 ZIP，保持目标型号资料可识别。':'请先在任务原知识库中补充对应型号的资料。'}本页暂不支持上传文件。</p><ul>{overview.material_requirements.map(m=><li key={m.request_id}><strong>{m.question || m.request_id}</strong><p>目标型号：{m.target_model}</p><p>需要：{m.document_types.join('；')}</p>{m.conditions.length>0&&<p>适用条件：{m.conditions.join('；')}</p>}</li>)}</ul><p>将重新读取原文和图片、提取事实并检查。历史版本保留；已有规划会重新生成，已授权舍弃的内容不会自动恢复。</p><label className="resolution-check"><input type="checkbox" disabled={disabled} checked={updated} onChange={e=>setUpdated(e.target.checked)}/><span>我已更新原资料源，重新读取并检查</span></label><button className="primary" disabled={disabled || !updated || !overview.actions.includes('refresh_evidence')} onClick={()=>perform('/refresh-evidence',{version:task.version})}><RefreshCw size={16} aria-hidden="true" />资料已更新，重新检查</button></> : <ManualEvidenceForm task={task} materials={overview.material_requirements} disabled={disabled||!overview.actions.includes('manual_evidence')} working={working} onDirty={setManualDirty} onSubmit={perform}/>}
      </section>}
      {mode==='modify' && <section className="resolution-preview"><h3>重新描述你的需求</h3><Field label="调整后的需求"><textarea value={instruction} disabled={disabled} maxLength={4000} onChange={e=>{setInstruction(e.target.value);setModifyConfirmed(false);}} placeholder="例如：以轻便为主，不再突出续航；面向日常上课携带电脑的学生…"/></Field><p>这是整体需求调整：当前策略、资料包、规划、文稿、核验及执行取舍将失效，历史记录保留。助手会重新分析，再请你确认策略。</p><label className="resolution-check"><input type="checkbox" disabled={disabled} checked={modifyConfirmed} onChange={e=>setModifyConfirmed(e.target.checked)}/><span>确认按新需求重新分析</span></label><button className="primary" disabled={disabled || instruction.trim().length<2 || !modifyConfirmed || !overview.actions.includes('modify_requirements')} onClick={()=>perform('/modify',{version:task.version,instruction:instruction.trim()})}>提交需求，重新分析</button></section>}
      {working && <p role="status"><LoaderCircle size={16} className="spin" aria-hidden="true" /> 正在提交，请稍候…</p>}
      <details className="brief-details"><summary>已有依据的内容（{overview.available_facts.length} 项）</summary><ul>{overview.available_facts.map(f=><li key={f.id}><button className="text-link" onClick={()=>onInspect({type:'fact',id:f.id})}>{f.claim}</button></li>)}</ul></details>
    </>}
    {!overview && !loading && <p className="muted"><AlertCircle size={16} aria-hidden="true" />审查概览尚未读取成功，不能据此授权取舍。原始事实仍可在下方查看。</p>}
  </section>;
}
