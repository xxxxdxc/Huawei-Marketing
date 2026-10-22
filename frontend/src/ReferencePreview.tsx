import { BookOpen, FileText } from 'lucide-react';
import { useState } from 'react';
import type { DemoContext, DemoPlatform, DemoPost } from './historyEffectsData';
import { DEMO_CAMPAIGNS, DEMO_POSTS, findDemoCampaign } from './historyEffectsData';
import { Badge, Empty, Field, PLATFORMS } from './shared';

export default function ReferencePreview({ ids, initial, onOpenPost, onBrowse }: { ids: string[]; initial?:DemoPost; onOpenPost:(id:string)=>void; onBrowse:()=>void }) {
  const [context,setContext]=useState<DemoContext>(initial?.campaignId||'campus');
  const [platform,setPlatform]=useState<DemoPlatform>(initial?.platform||'xiaohongshu');
  const campaign=findDemoCampaign(context);
  const matches=DEMO_POSTS.filter(post=>ids.includes(post.id)&&post.platform===platform&&post.campaignId===context);
  return <section className="reference-preview"><div className="reference-preview-intro"><span className="icon-box"><BookOpen size={22} aria-hidden="true" /></span><div><h3>好写法，可以带到下一篇</h3><p>选择一项相似任务，查看演示案例如何成为写作参考。</p></div></div><p className="notice">功能原型：按平台与场景筛选本浏览器的演示收藏。以下结果尚未被真实 Writer 加载。</p>
    <div className="reference-preview-fields"><Field label="演示营销场景"><select value={context} onChange={e=>setContext(e.target.value as DemoContext)}>{DEMO_CAMPAIGNS.map(item=><option value={item.id} key={item.id}>{item.scene} · {item.audience}</option>)}</select></Field><Field label="演示发布平台"><select value={platform} onChange={e=>setPlatform(e.target.value as DemoPlatform)}>{Object.entries(PLATFORMS).map(([id,label])=><option value={id} key={id}>{label}</option>)}</select></Field></div>
    <div className="reference-example-task"><span>模拟下一次任务</span><p>为{campaign.audience}，围绕{campaign.scene}，准备一篇{PLATFORMS[platform]}图文。</p></div>
    <div className="reference-result-heading"><h3>可参考的案例</h3><span role="status" aria-atomic="true">{matches.length} 篇匹配 · 平台与场景一致</span></div>
    {matches.length?matches.map(post=><article className="reference-match" key={post.id}><div><Badge>模拟匹配</Badge><h4>{post.title}</h4><p>{campaign.audience} · {campaign.scene}</p></div><dl><dt>开头可参考</dt><dd>{post.lessons.opening}</dd><dt>组织方式</dt><dd>{post.lessons.structure.join(' → ')}</dd><dt>表达与行动</dt><dd>{post.lessons.voice} {post.lessons.cta}</dd></dl><button className="text-link" type="button" onClick={()=>onOpenPost(post.id)}><FileText size={14} aria-hidden="true" />查看原示例与表现</button></article>):<Empty icon={<BookOpen />} title={ids.length?'这个平台和场景还没有收藏':'先留下一篇好案例'} text={ids.length?'可以换一个平台或场景，或到演示任务中加入相应推文。':'打开示例推文，加入优秀案例库后，再回到这里查看参考结果。'} action={<button className="secondary" type="button" onClick={onBrowse}>浏览演示任务</button>} />}
    <p className="history-fact-boundary">只参考写作方法，不沿用旧文的产品参数、价格、优惠或体验结论。</p>
  </section>;
}
