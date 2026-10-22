import { BookOpen, BookmarkPlus, BookmarkCheck, LoaderCircle, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { DemoPost } from './historyEffectsData';
import { demoDate, findDemoCampaign, metricText } from './historyEffectsData';
import { Badge, PLATFORMS } from './shared';
import HistoryPostPreview from './HistoryPostPreview';

export function PostMetrics({ post }: { post: DemoPost }) {
  const metrics: [string, number | null][] = [['浏览 / 阅读',post.metrics.views],['点赞',post.metrics.likes],['收藏',post.metrics.saves],['评论',post.metrics.comments]];
  return <dl className="history-post-metrics">{metrics.map(([label,value])=><div key={label}><dt>{label}</dt><dd aria-label={value===null?`${label}：未提供数据`:undefined}>{metricText(value)}</dd></div>)}</dl>;
}
export function LessonList({ post, compact = false }: { post: DemoPost; compact?: boolean }) {
  return <dl className={`history-lessons ${compact?'is-compact':''}`}><dt>标题技巧</dt><dd>{post.lessons.title}</dd><dt>开头方式</dt><dd>{post.lessons.opening}</dd><dt>正文结构</dt><dd>{post.lessons.structure.join(' → ')}</dd><dt>语言风格</dt><dd>{post.lessons.voice}</dd><dt>行动引导</dt><dd>{post.lessons.cta}</dd></dl>;
}
export default function HistoryPostDetail({ post, saved, warning, onAdd, onRemove, onPreview }: { post: DemoPost; saved: boolean; warning: string; onAdd: (id: string)=>void; onRemove:(id:string)=>void; onPreview:(post:DemoPost)=>void }) {
  const campaign = findDemoCampaign(post.campaignId);
  const [analyzing,setAnalyzing]=useState(false);
  const timer=useRef<number|null>(null);
  const nextAction=useRef<HTMLButtonElement>(null);
  useEffect(()=>()=>{if(timer.current!==null)window.clearTimeout(timer.current);},[]);
  function add() { if(analyzing||saved)return;setAnalyzing(true);timer.current=window.setTimeout(()=>{onAdd(post.id);setAnalyzing(false);timer.current=null;requestAnimationFrame(()=>nextAction.current?.focus({preventScroll:true}));},650); }
  return <div className="history-post-detail"><div className="history-detail-meta"><Badge>功能原型 · 模拟数据</Badge><span>{PLATFORMS[post.platform]}</span><span>{campaign.audience} · {campaign.scene}</span></div>
    <p className="history-simulation-note">推文、配图、表现和分析均为预置示例，未实际发布；案例尚未接入真实 Writer References，不作为产品事实。</p>
    <div className="history-detail-grid"><section className="history-detail-content" aria-label="示例推文全文"><HistoryPostPreview post={post} /><dl className="history-source-meta"><dt>演示发布时间</dt><dd>{demoDate(post.publishedAt,true)}</dd><dt>发布链接</dt><dd>未实际发布，无真实推文链接</dd><dt>示例来源</dt><dd>{campaign.name}<small>{post.id}</small></dd></dl></section>
      <aside className="history-detail-side"><section className="history-performance"><h3>表现快照</h3><PostMetrics post={post} /><p>来源：预置演示数据</p><p>数据日期：{demoDate(post.observedAt,true)}</p>{post.platform==='moments'&&<p>本示例未提供朋友圈浏览、收藏数据，以“—”显示。</p>}</section>
        <section className="history-learning" aria-busy={analyzing}><div className="history-learning-heading"><BookOpen size={19} aria-hidden="true" /><h3>{saved?'已加入演示案例库':'留下这篇的好写法'}</h3></div>{warning&&<p className="notice warning" role="alert">{warning}</p>}
          {saved?<><div className="history-case-tags"><span>{PLATFORMS[post.platform]}</span><span>{campaign.audience}</span><span>{campaign.scene}</span></div><p className="history-case-status" role="status" aria-atomic="true"><BookmarkCheck size={15} aria-hidden="true" />{warning?'已加入当前页面，尚未确认持久保存':'案例卡已保存在当前浏览器'}</p>{warning&&<p className="muted">保存状态以上方提示为准。</p>}<div className="history-case-actions"><button ref={nextAction} className="primary" type="button" onClick={()=>onPreview(post)}>预览下次参考</button><button className="text-link history-remove" type="button" onClick={()=>onRemove(post.id)}><Trash2 size={14} aria-hidden="true" />移出优秀案例库</button></div><LessonList post={post} /><p className="history-fact-boundary">只借鉴写作方法；产品参数、价格和优惠须按新任务重新查证。</p></>:<><p>展示标题、开头、结构与语气的示例分析，作为后续创作的参考卡。</p><button className="primary" type="button" disabled={analyzing} onClick={add}>{analyzing?<LoaderCircle size={17} className="spin" aria-hidden="true" />:<BookmarkPlus size={17} aria-hidden="true" />}{analyzing?'正在模拟提炼…':'加入优秀案例库'}</button>{analyzing?<p role="status">正在整理预置案例分析，不调用模型；关闭面板会取消本次操作。</p>:<small>仅保存演示收藏，尚未写入真实 Writer References。</small>}</>}
        </section>
      </aside>
    </div>
  </div>;
}
