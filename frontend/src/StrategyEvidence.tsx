import { useState } from 'react';
import { ArrowRight, LoaderCircle, Search, Sparkles } from 'lucide-react';
import type { Brief, Task } from './types';
import { Badge, effectiveStatus, Empty, Field, PLATFORMS, type Act } from './shared';
import BriefConversation, { ConversationHistory } from './BriefConversation';
export type { Act } from './shared';

function LegacyStrategy({ task, locked, act, onDirty }: { task: Task; locked: boolean; act: Act; onDirty: (dirty: boolean) => void }) {
  const [brief, setBrief] = useState<Brief | null>(() => task.brief ? structuredClone(task.brief) : null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const state = effectiveStatus(task);
  const editable = !locked && ['brief_ready', 'needs_information'].includes(state);
  function change<K extends keyof Brief>(key: K, value: Brief[K]) { setBrief(b => b ? { ...b, [key]: value } : b); onDirty(true); }
  if (!brief) return <Empty icon={<Sparkles />} title={locked ? '正在理解营销任务…' : '准备分析营销任务'} text="提取人群、场景、目标与平台后，会先请你确认营销策略。" action={!locked && state === 'draft' ? <button className="primary" onClick={() => act('/analyze', { version: task.version })}>开始分析需求</button> : undefined} />;
  async function supplement() {
    const instruction = brief!.questions.map((q, i) => `${q}\n补充回答：${answers[i] || ''}`).join('\n');
    await act('/modify', { version: task.version, instruction });
  }
  return <><div className="section-heading"><div><p className="overline">第一次确认</p><h2>{editable ? '确认这次营销的方向' : '已确认的营销方向'}</h2><p>先对齐目标，再查证产品事实。</p></div><Badge>{editable ? '等待你确认' : '策略记录'}</Badge></div>
    <details className="original-task"><summary>查看原始任务</summary><p>{task.raw}</p></details>
    {brief.questions.length > 0 && <section className="questions-panel"><h3>还需要补充这些信息</h3><p>在这里回答即可；助手会结合回答重新整理策略。</p><fieldset disabled={!editable}>{brief.questions.map((q, i) => <Field key={`${i}-${q}`} label={q}><textarea value={answers[i] || ''} onChange={e => { setAnswers(a => ({ ...a, [i]: e.target.value })); onDirty(true); }} maxLength={500} /></Field>)}<button type="button" className="primary" disabled={brief.questions.some((_, i) => !answers[i]?.trim()) || brief.questions.map((q,i) => q + (answers[i] || '')).join('').length > 3500} onClick={supplement}>补充信息，更新策略</button></fieldset></section>}
    <form onSubmit={e => { e.preventDefault(); if (editable && brief.questions.length === 0) void act('/confirm-brief', { version: task.version, brief }); }}><fieldset disabled={!editable}><div className="two-fields"><Field label="目标人群"><input required maxLength={300} value={brief.audience} onChange={e => change('audience', e.target.value)} /></Field><Field label="使用场景"><input required maxLength={300} value={brief.scenario} onChange={e => change('scenario', e.target.value)} /></Field><Field label="营销目标"><input required maxLength={300} value={brief.goal} onChange={e => change('goal', e.target.value)} /></Field><Field label="购买阶段"><input required maxLength={100} value={brief.purchase_stage} onChange={e => change('purchase_stage', e.target.value)} /></Field><Field label="发布平台"><select value={brief.platform} onChange={e => change('platform', e.target.value)}>{Object.entries(PLATFORMS).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></Field><Field label="表达语气"><input value={brief.tone} onChange={e => change('tone', e.target.value)} /></Field></div><Field label="优先回应的需求（每行一项）"><textarea value={brief.pain_points.join('\n')} onChange={e => change('pain_points', e.target.value.split('\n'))} /></Field><Field label="营销策略"><textarea rows={4} required maxLength={2000} value={brief.strategy} onChange={e => change('strategy', e.target.value)} /></Field><Field label="希望查证的卖点方向（每行一项）" hint="此时是查证方向，具体产品能力以接下来读取的资料为准。"><textarea value={brief.emphasis.join('\n')} onChange={e => change('emphasis', e.target.value.split('\n'))} /></Field></fieldset>{['brief_ready', 'needs_information'].includes(state) && <div className="action-bar"><span><Search size={16} aria-hidden="true" />确认后读取原文与图片</span><button className="primary" type="submit" disabled={!editable || brief.questions.length > 0}>确认策略，查资料<ArrowRight size={17} aria-hidden="true" /></button></div>}</form>
  </>;
}

export function Strategy(props: { task: Task; locked: boolean; act: Act; onDirty: (dirty: boolean) => void }) {
  if (!props.task.brief_analysis && props.task.status === 'analyzing') return <div className="brief-conversation"><ConversationHistory task={props.task} /><div className="assistant-message"><div className="chat-thinking" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" />正在理解你的需求，整理产品、人群和场景…</div><p className="muted">{props.task.events.at(-1)?.text || '分析完成后，会在这里与你确认方向。'}</p></div></div>;
  return props.task.brief_analysis ? <BriefConversation {...props} /> : <div className="brief-conversation"><ConversationHistory task={props.task} /><div className="assistant-message"><LegacyStrategy {...props} /></div></div>;
}
