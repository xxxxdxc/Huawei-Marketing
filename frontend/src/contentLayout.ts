import type { Doc, Plan } from './types';
export type LayoutSlot={section_id:string;image_id:string;kind:string;order:number};
export function imageLayout(plan:Plan|null,platform:string,doc?:Doc):LayoutSlot[]{
 const paragraphs=new Map(doc?.paragraphs.map(p=>[p.section_id,p]));let index=0;
 const sections=plan?.sections || doc?.paragraphs.map(p=>({id:p.section_id,image_id:p.image_id,image_position:undefined})) || [];
 const slots:LayoutSlot[]=[];
 for(const section of sections){
  const paragraph=paragraphs.get(section.id);const id=paragraph?paragraph.image_id:section.image_id;if(!id)continue;index++;
  const p=section.image_position;
  slots.push({section_id:section.id,image_id:id,kind:p&&p.kind!=='none'?p.kind:platform==='wechat'?'after_section':platform==='xiaohongshu'?'carousel':'grid',order:p?.order || index});
 }
 return platform==='wechat'?slots:slots.sort((a,b)=>a.order-b.order);
}
export function sequenceImages<T extends {image_id:string|null;image_position?:{kind:string;order?:number|null}|null}>(sections:T[],platform:string):T[]{
 let index=0;return sections.map(s=>{if(!s.image_id)return {...s,image_position:{kind:'none',order:null}};index++;return {...s,image_position:platform==='wechat'?{kind:s.image_position?.kind==='before_section'?'before_section':'after_section',order:null}:{kind:platform==='xiaohongshu'?'carousel':'grid',order:index}};});
}
