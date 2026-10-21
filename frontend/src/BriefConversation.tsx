import { useState } from 'react';
import { ArrowUp, LoaderCircle, Search, Sparkles } from 'lucide-react';
import type { Task } from './types';
import StrategyDirections from './StrategyDirections';
import { BUSY, Field, PLATFORMS, effectiveStatus, type Act } from './shared';

export function ConversationHistory({ task }: { task: Task }) {
  const turns = task.dialogue?.length ? task.dialogue : [{ id: 'original', kind: 'user', text: task.raw }];
  return <div className="conversation-history">{turns.map(turn => <div key={turn.id}>{'question' in turn && turn.question && <div className="assistant-history">{turn.question}</div>}<div className={turn.kind === 'selection' ? 'selection-message' : 'user-message'}><span className="sr-only">你的输入：</span>{turn.text}</div></div>)}</div>;
}
export default function BriefConversation({ task, locked, act, onDirty }: { task: Task; locked: boolean; act: Act; onDirty: (value: boolean) => void }) {
  const analysis = task.brief_analysis!;
  const [answers, setAnswers] = useState<Record<string, string>>({}), [feedback, setFeedback] = useState('');
  const editable = !locked && ['brief_ready', 'needs_information'].includes(effectiveStatus(task));
  const busy = BUSY.includes(task.status);
  function changeAnswer(id: string, value: string) { const next = { ...answers, [id]: value }; setAnswers(next); onDirty(Boolean(feedback.trim() || Object.values(next).some(v => v.trim()))); }
  const entries = analysis.questions.filter(q => answers[q.id]?.trim()).map(q => ({ question_id: q.id, answer: answers[q.id].trim() }));
  const labels: Record<string,string> = { product_model: '产品型号', target_audience: '目标人群', scenario: '使用场景', platform: '发布平台', marketing_goal: '营销目标', buying_stage: '购买阶段' };
  return <div className="brief-conversation"><ConversationHistory task={task} />
    <section className="assistant-message"><div className="assistant-identity"><span><Sparkles size={19} aria-hidden="true" /></span>华为 PC 图文助手</div>
      {busy ? <div className="chat-thinking" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" />正在结合你的回答整理需求与策略…</div> : <>
        {analysis.questions.length > 0 ? <><h2>{analysis.status === 'needs_resolution' ? '有几个要求需要和你核对' : '再聊清这几个细节，就可以开始了'}</h2><form onSubmit={e => { e.preventDefault(); if (entries.length) void act('/brief/answers', { version: task.version, answers: entries }); }}><fieldset disabled={!editable}>{analysis.questions.map(q => <section className="chat-question" key={q.id}><Field label={q.question} hint={q.reason}><textarea value={answers[q.id] || ''} maxLength={2000} onChange={e => changeAnswer(q.id, e.target.value)} placeholder="输入你的回答…" /></Field>{q.choices.length > 0 && <div className="answer-choices">{q.choices.map(choice => <button key={choice} type="button" aria-pressed={answers[q.id] === choice} onClick={() => changeAnswer(q.id, choice)}>{choice}</button>)}</div>}</section>)}<div className="chat-send-row"><span>可以先回答已确定的问题</span><button className="primary" disabled={!entries.length || Boolean(feedback.trim())}><ArrowUp size={17} aria-hidden="true" />发送回答</button></div></fieldset></form></> : <><h2>这是我理解的营销方向</h2><p className="muted">{task.package ? '策略保留为创作依据，下面的标签已按当前检索结果更新。' : '先确认要验证的方向，确认后再读取产品原文与图片；此时不承诺产品能力。'}</p><dl className="brief-summary">{Object.entries(labels).map(([key, label]) => { const field = analysis.requirements[key]; if (!field) return null; const value = Array.isArray(field.value) ? field.value.join('、') : field.value; return <div key={key}><dt>{label}<small>{({ explicit: '你已明确', inferred: '根据需求推断', unknown: '待明确' } as Record<string,string>)[field.source] || field.source}</small></dt><dd>{key === 'platform' ? PLATFORMS[value || ''] || value || '待明确' : value || '待明确'}{field.reason && <details><summary>查看判断依据</summary><p>{field.reason}</p>{field.evidence.map((ev, i) => <blockquote key={i}>{ev.quote}</blockquote>)}</details>}</dd></div>; })}</dl>
          <StrategyDirections task={task} />
          <details className="brief-details"><summary>查看人群洞察与资料检索计划</summary>{analysis.audience_insight && <><h3>主要需求</h3><p>{analysis.audience_insight.job_to_be_done}</p><ul>{analysis.audience_insight.problems.map(p => <li key={p}>{p}</li>)}</ul>{analysis.audience_insight.decision_factors.map(p => <p key={p.point}><strong>{p.point}</strong>：{p.reason}</p>)}</>}{analysis.retrieval_plan && <><h3>准备查证的事实</h3><ul>{analysis.retrieval_plan.facts.map(r => <li key={r.id}>{r.question}</li>)}</ul><h3>准备查找的图片</h3><ul>{analysis.retrieval_plan.images.map(r => <li key={r.id}>{r.description}</li>)}</ul></>}</details>
          {['brief_ready', 'needs_information'].includes(effectiveStatus(task)) && <div className="chat-confirm"><p>确认后开始检索资料，整理出有依据的候选卖点后，还会请你确认本篇重点。</p><button className="primary" disabled={!editable || analysis.status !== 'ready' || !task.brief_analysis_hash || Boolean(feedback.trim())} onClick={() => act('/confirm-brief', { version: task.version, analysis_hash: task.brief_analysis_hash })}><Search size={17} aria-hidden="true" />确认策略，查资料</button></div>}</>}
      </>}
    </section>
    {['brief_ready', 'needs_information'].includes(effectiveStatus(task)) && <form className="chat-followup" onSubmit={e => { e.preventDefault(); if (feedback.trim().length >= 2) void act('/modify', { version: task.version, instruction: feedback.trim() }); }}><Field label="补充或调整想法"><textarea maxLength={4000} value={feedback} disabled={!editable} onChange={e => { setFeedback(e.target.value); onDirty(Boolean(e.target.value.trim() || Object.values(answers).some(v => v.trim()))); }} placeholder="例如：更侧重家长关心的学习场景，语气自然一些…" /></Field><button className="primary" disabled={!editable || feedback.trim().length < 2 || Object.values(answers).some(v => v.trim())}><ArrowUp size={17} aria-hidden="true" />发送调整</button></form>}
  </div>;
}
