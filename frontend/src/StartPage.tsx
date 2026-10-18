import { useEffect, useState } from 'react';
import { ArrowUp, BookOpen, BriefcaseBusiness, ChevronDown, Laptop, LoaderCircle, MessageCircle, ShieldCheck, Sparkles } from 'lucide-react';
import type { Product } from './types';
import { Field, PLATFORMS } from './shared';

export default function StartPage({ products, catalogState, catalogError, hasKey, pending, onCreate, onSettings, onReconnect, onDirty }: { products: Product[]; catalogState: string; catalogError: string; hasKey: boolean; pending: boolean; onCreate: (raw: string, product: string, platform: string) => Promise<boolean>; onSettings: () => void; onReconnect: () => void; onDirty: (dirty: boolean) => void }) {
  const [raw, setRaw] = useState(''), [product, setProduct] = useState(''), [platform, setPlatform] = useState('');
  const [audience, setAudience] = useState(''), [scenario, setScenario] = useState(''), [tone, setTone] = useState(''), [goal, setGoal] = useState('');
  const [validation, setValidation] = useState('');
  useEffect(() => onDirty(Boolean(raw || product || platform || audience || scenario || tone || goal)), [raw, product, platform, audience, scenario, tone, goal, onDirty]);
  const assembled = [raw.trim(), audience.trim() && `补充目标人群：${audience.trim()}`, scenario.trim() && `补充营销场景：${scenario.trim()}`, tone.trim() && `表达语气：${tone.trim()}`, goal.trim() && `希望读者采取的行动：${goal.trim()}`].filter(Boolean).join('\n');
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!hasKey) { setValidation('请先到连接设置配置模型服务，再开始分析。'); return; }
    if (assembled.length > 6000) { setValidation('任务描述和补充信息合计不能超过 6000 字，请缩短后再试。'); return; }
    setValidation(''); await onCreate(assembled, product, platform);
  }
  const examples = [
    { title: '开学购机', subtitle: '把产品卖点，放进校园日常', Icon: BookOpen, text: '面向准备开学购机的大学新生与家长，围绕课堂、图书馆和宿舍学习，介绍这款电脑有依据的相关卖点，引导到店体验。' },
    { title: '移动办公', subtitle: '从通勤到出差，讲清使用价值', Icon: BriefcaseBusiness, text: '面向经常出差的职场用户，围绕通勤、差旅办公和会议材料处理，介绍这款电脑有依据的相关卖点，引导咨询和到店体验。' },
    { title: '产品种草', subtitle: '一篇有依据的小红书图文', Icon: Laptop, text: '帮我写一篇小红书产品种草图文，用真实产品资料讲清适合的人群、使用场景和购买前需要了解的条件。' },
    { title: '门店朋友圈', subtitle: '简短介绍，自然邀请到店体验', Icon: MessageCircle, text: '帮我写一条门店朋友圈，围绕产品最值得关注的特点，用亲切简短的表达邀请顾客到店了解体验。' },
  ];
  return <div className="start-page conversation-home"><header className="home-heading"><span className="home-eyebrow"><Sparkles size={16} aria-hidden="true" />华为 PC · 图文创作助手</span><h1>聊聊你的想法，让产品被看见</h1><p>从一句需求开始，把产品事实写成打动人的图文。</p></header>
    <form className="composer surface prompt-composer" onSubmit={submit}><fieldset disabled={pending}>
      <div className="prompt-options"><Field label="产品型号"><select value={product} disabled={catalogState !== 'ready'} onChange={e => setProduct(e.target.value)}><option value="">{catalogState === 'loading' ? '目录读取中…' : '可选，也可以直接描述'}</option>{[...new Set(products.map(p => p.category))].map(c => <optgroup key={c} label={c}>{products.filter(p => p.category === c).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</optgroup>)}</select></Field><Field label="发布平台"><select value={platform} onChange={e => setPlatform(e.target.value)}><option value="">可选，稍后确定</option>{Object.entries(PLATFORMS).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></Field></div>
      <Field label="营销任务"><textarea className="task-input" required minLength={4} maxLength={6000} value={raw} onChange={e => setRaw(e.target.value)} placeholder="告诉我你想推广哪款华为电脑、写给谁看。例如：帮我为大学新生写一篇 MateBook 小红书图文，突出校园学习场景…" /></Field>
      <details className="advanced"><summary>补充信息 <span>人群、场景、语气，按需填写</span><ChevronDown size={16} aria-hidden="true" /></summary><div className="two-fields"><Field label="目标人群"><input value={audience} onChange={e => setAudience(e.target.value)} maxLength={300} placeholder="例如：大学新生…" /></Field><Field label="营销场景"><input value={scenario} onChange={e => setScenario(e.target.value)} maxLength={300} placeholder="例如：开学购机…" /></Field><Field label="表达语气"><input value={tone} onChange={e => setTone(e.target.value)} maxLength={200} placeholder="例如：亲切、清楚…" /></Field><Field label="行动目标"><input value={goal} onChange={e => setGoal(e.target.value)} maxLength={300} placeholder="例如：到店体验…" /></Field></div></details>
      {validation && <p className="notice warning" role="alert">{validation}</p>}
      <div className="composer-footer"><span><ShieldCheck size={17} aria-hidden="true" />先聊清方向，再查资料与创作</span><button className="primary send-button" type="submit" disabled={pending}>{pending ? <LoaderCircle size={19} className="spin" aria-hidden="true" /> : <ArrowUp size={19} aria-hidden="true" />}{pending ? '正在发送…' : '发送'}</button></div>
    </fieldset></form>
    {(catalogError || (catalogState === 'ready' && products.length === 0)) && <div className="notice warning" role="alert"><p>{catalogError || '产品目录为空，请确认知识库访问权限。'}你仍可先输入需求。</p><button type="button" className="text-link" onClick={onReconnect}>重新读取知识库</button></div>}
    {!hasKey && <div className="setup-note"><span>开始前，请先连接模型服务。</span><button type="button" className="text-link" disabled={pending} onClick={onSettings}>前往连接设置</button></div>}
    <section className="scenario-section" aria-label="场景灵感"><h2>从一个场景开始</h2><div className="scenario-grid">{examples.map(({ title, subtitle, Icon, text }, i) => <button disabled={pending} type="button" key={title} aria-label={title} className={`scenario-card scenario-${i}`} onClick={() => { setRaw(text); document.querySelector<HTMLTextAreaElement>('.task-input')?.focus(); }}><span className="scenario-icon"><Icon size={24} strokeWidth={1.8} aria-hidden="true" /></span><span><strong>{title}</strong><small>{subtitle}</small></span></button>)}</div></section>
    <p className="home-footnote">产品资料来自指定 ima 知识库 · 策略与内容规划由你确认</p>
  </div>;
}
