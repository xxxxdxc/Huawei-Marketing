import { useState } from 'react';
import { BookOpen, FileText, ImageIcon, Search } from 'lucide-react';
import type { Task } from './types';
import { AssetImage, Badge, Empty, localTime, sourceLabel } from './shared';
import Dialog from './Dialog';
import EvidenceCoverage from './EvidenceCoverage';

export type EvidenceTarget = { type: 'fact' | 'image' | 'source'; id: string };
export function EvidenceDialog({ task, target, onClose }: { task: Task; target: EvidenceTarget; onClose: () => void }) {
  const pkg = task.package;
  if (!pkg) return null;
  const fact = target.type === 'fact' ? [...pkg.facts, ...(pkg.all_facts || [])].find(f => f.id === target.id) : null;
  const asset = target.type === 'image' ? [...pkg.images, ...(pkg.asset_candidates || [])].find(i => i.id === target.id) : null;
  const source = pkg.sources.find(s => s.id === (fact?.source_id || (target.type === 'source' ? target.id : '')));
  const index = fact && source ? source.text.indexOf(fact.quote) : -1;
  return <Dialog title={fact ? '事实与原文依据' : asset ? '图片来源与适用范围' : '原始资料'} onClose={onClose} wide>
    <p className="muted">当前产品：{pkg.product.name}</p>
    {fact && !pkg.facts.some(f => f.id === fact.id) && <p className="notice warning">此事实仅供追溯，未纳入当前可用内容。</p>}
    {fact && <><h3 className="evidence-title">{fact.claim}</h3><blockquote className="source-quote">{fact.quote}</blockquote><div className="notice">适用条件：{fact.conditions || '该条摘录未另列条件，请结合完整原文审阅。'}</div></>}
    {asset && <>{!pkg.images.some(i => i.id === asset.id) && <p className="notice warning">此图片仅供追溯，未纳入当前可用素材。</p>}<AssetImage asset={asset} /><h3 className="evidence-title">{asset.description || asset.name}</h3><dl className="detail-list"><dt>型号</dt><dd>{asset.model}</dd><dt>来源</dt><dd>{sourceLabel(asset.source)}</dd><dt>选用理由</dt><dd>{asset.selection_reason || '未提供额外选用说明'}</dd><dt>画面检查</dt><dd>{asset.visual_checked ? '已执行画面检查；整篇仍需完整核验' : '尚未检查实际画面'}</dd></dl></>}
    {source && <>{source.source_type==='user_manual' && <p className="notice warning">用户补充，链接未独立验证；这里只核对资料原文与文稿的一致性。</p>}<h3 className="evidence-title">{source.title}</h3><p className="source-path">{sourceLabel(source.path)}</p><p className="muted">读取时间：{localTime(source.retrieved_at)}</p><div className="source-text" tabIndex={0} aria-label="完整原文">{index >= 0 && fact ? <>{source.text.slice(0, index)}<mark>{fact.quote}</mark>{source.text.slice(index + fact.quote.length)}</> : source.text}</div>{fact && index < 0 && <p className="muted">未找到完全相同的连续摘录，请对照原文检查空格、断行与内容。</p>}</>}
    {!fact && !asset && !source && <p className="notice">该项依据在当前版本中不存在，请重新载入任务。</p>}
  </Dialog>;
}
export default function Evidence({ task, onInspect }: { task: Task; onInspect: (target: EvidenceTarget) => void }) {
  const [view, setView] = useState('facts');
  const pkg = task.package;
  if (!pkg) return <Empty icon={<BookOpen />} title="资料会在策略确认后出现" text="助手会读取指定型号原文，整理事实和图片；你可以在这里追溯每项依据。" />;
  return <><div className="section-heading"><div><h2>知识库依据</h2><p>{pkg.product.name} 的事实、素材与完整原文</p></div><Badge>已读取资料</Badge></div>
    {pkg.conflicts.length > 0 && <div className="notice warning" role="alert"><strong>资料存在冲突，暂不能作为最终稿导出</strong><ul>{pkg.conflicts.map((c, i) => <li key={i}>{typeof c === 'string' ? c : c.detail}{typeof c !== 'string' && c.source_ids.map(id => <button key={id} className="text-link" onClick={() => onInspect({ type: 'source', id })}>查看来源 {id}</button>)}</li>)}</ul></div>}
    <EvidenceCoverage task={task} onInspect={onInspect} />
    <div className="segmented" aria-label="资料分类">{[['facts', `事实 ${pkg.facts.length}`], ['images', `图片 ${pkg.images.length}`], ['sources', `原文 ${pkg.sources.length}`]].map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div>
    {view === 'facts' && <div className="fact-list">{pkg.facts.length === 0 ? <Empty title="尚未提取到可用事实" text="请查看原始资料与任务状态，确认是否存在证据缺失。" /> : pkg.facts.map((f, i) => <article className="fact-card" key={f.id}><div className="fact-heading"><span className="fact-number">{i + 1}</span><h3>{f.claim}</h3></div><blockquote>{f.quote}</blockquote>{f.conditions && <p className="conditions">限定条件：{f.conditions}</p>}<div className="fact-footer"><span><FileText size={14} aria-hidden="true" />{pkg.sources.find(s => s.id === f.source_id)?.title || '来源待核对'}</span><button className="text-link" onClick={() => onInspect({ type: 'fact', id: f.id })}>查看原文依据</button></div></article>)}</div>}
    {view === 'images' && <div className="asset-grid">{pkg.images.length === 0 ? <Empty icon={<ImageIcon />} title="没有可用图片" text="需要指定型号的知识库素材，无法使用外部图片补齐。" /> : pkg.images.map(im => <article className="asset-card" key={im.id}><AssetImage asset={im} /><div><h3>{im.description || im.name}</h3><p>{im.selection_reason || im.model}</p><button className="text-link" onClick={() => onInspect({ type: 'image', id: im.id })}>查看图片来源</button></div></article>)}</div>}
    {view === 'sources' && <div className="source-list">{pkg.sources.map(s => <button key={s.id} className="source-row" onClick={() => onInspect({ type: 'source', id: s.id })}><FileText size={21} aria-hidden="true" /><span><strong>{s.title}</strong><small>{sourceLabel(s.path)}</small></span><Search size={17} aria-hidden="true" /></button>)}</div>}
  </>;
}
