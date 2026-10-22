import {useEffect,useState} from 'react';
import type {Task} from './types';
import {Field} from './shared';

type Material={request_id:string;question?:string;target_model:string};
type Props={task:Task;materials:Material[];disabled:boolean;working:boolean;onDirty:(v:boolean)=>void;onSubmit:(path:string,body:unknown)=>void};
export default function ManualEvidenceForm({task,materials,disabled,working,onDirty,onSubmit}:Props){
 const [requests,setRequests]=useState<string[]>([]),[text,setText]=useState(''),[url,setUrl]=useState(''),[title,setTitle]=useState(''),[conditions,setConditions]=useState(''),[confirmed,setConfirmed]=useState(false);
 useEffect(()=>{onDirty(Boolean(requests.length||text||url||title||conditions));},[requests,text,url,title,conditions,onDirty]);
 let validUrl=false;try{const u=new URL(url.trim());validUrl=['http:','https:'].includes(u.protocol)&&!!u.hostname&&!u.username&&!u.password&&!/\s/.test(url.trim());}catch{/* Incomplete input stays local. */}
 const change=()=>setConfirmed(false);
 return <section aria-label="手动补充文字依据">
  <h4>手动补充文字依据</h4>
  <p>当前型号：{task.package?.product.name}。仅用于本任务，不修改 ZIP 或 ima 知识库，也不增加图片。</p>
  <fieldset disabled={disabled}><legend>这份资料要补充哪些需求？</legend>{materials.map(m=><label className="resolution-check" key={m.request_id}><input type="checkbox" checked={requests.includes(m.request_id)} onChange={e=>{setRequests(r=>e.target.checked?[...r,m.request_id]:r.filter(id=>id!==m.request_id));change();}}/><span>{m.question||m.request_id}{task.execution_scope?.omitted_request_ids.includes(m.request_id)&&<small>此前已省略，补资料不会自动恢复此方向</small>}</span></label>)}</fieldset>
  <Field label="资料原文" hint="至少32字；系统会将摘录与此原文逐字核对。"><textarea disabled={disabled} value={text} maxLength={20000} rows={7} onChange={e=>{setText(e.target.value);change();}} placeholder="粘贴含产品型号、具体配置及测试条件的完整原文。只填一个数字或宣传结论不能直接通过检查。"/></Field>
  <Field label="来源链接" hint={url&&!validUrl ? '请填写完整 HTTP/HTTPS 链接，不能含账号密码或空格。' : '链接仅用于追溯，本轮不会自动读取或独立验证网页。'}><input disabled={disabled} type="url" aria-invalid={Boolean(url)&&!validUrl} value={url} maxLength={2000} onChange={e=>{setUrl(e.target.value);change();}} placeholder="https://…"/></Field>
  <Field label="来源名称（可选）"><input disabled={disabled} value={title} maxLength={200} onChange={e=>{setTitle(e.target.value);change();}} placeholder="例如：产品规格页"/></Field>
  <Field label="配置与适用条件补充（可选）"><textarea disabled={disabled} value={conditions} maxLength={1500} onChange={e=>{setConditions(e.target.value);change();}} placeholder="作为补充说明保存；不能替代原文中的测试条件依据。"/></Field>
  <p>提交后合并现有原文检查缺口与冲突，不重跑需求分析。旧规划和核验会失效，历史版本保留；通过后仍需确认核心卖点。</p>
  <p className="notice">用户补充，链接未独立验证。资料支持仅表示与所提供原文相符，不代表已核实网页或原文真实性。</p>
  <label className="resolution-check"><input type="checkbox" disabled={disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>我确认原文与来源对应，同意将其保存到当前任务并重新检查</span></label>
  <button className="primary" disabled={disabled||!requests.length||text.trim().length<32||!validUrl||!confirmed} onClick={()=>onSubmit('/manual-evidence',{version:task.version,product_id:task.product_id,request_ids:requests,text:text.trim(),source_url:url.trim(),source_title:title.trim(),conditions:conditions.trim(),confirmed:true})}>{working?'正在提交…':'提交原文，重新检查'}</button>
 </section>;
}
