import {test,expect} from '@playwright/test';
import {makeTask,mockApi,watermark} from './fixtures';
import {publicationText} from '../src/publicationText';

test('publication text omits internal headings and retains real text and captions',()=>{
 const doc=makeTask().document!;
 doc.paragraphs[0].heading='STAFF_GUIDE_ONLY';
 expect(publicationText(doc)).not.toContain('STAFF_GUIDE_ONLY');
 expect(publicationText(doc,true)).not.toContain('STAFF_GUIDE_ONLY');
 expect(publicationText(doc)).toContain(doc.paragraphs[0].text);
 expect(publicationText(doc,true)).toContain(doc.paragraphs[0].caption);
 expect(publicationText(doc)).toContain(doc.title);
});

for(const platform of ['xiaohongshu','wechat','moments']){
 test(platform+' hides paragraph headings while staff navigation and legacy body remain',async({page})=>{
  const t=makeTask('approved',platform),d=t.document!;
  d.paragraphs.forEach((p,i)=>p.heading='STAFF_GUIDE_'+i);
  const note='旧稿说明：实际尺寸和重量会因配置、制造工艺和测量方法有所差异。';
  d.lead=note;
  const before=structuredClone(d),state=await mockApi(page,t);
  await page.goto('/');
  const preview=page.locator('.platform-preview');
  await expect(preview).not.toContainText('STAFF_GUIDE');
  await expect(preview.locator('h4')).toHaveCount(0);
  await expect(preview).toContainText(note);
  await expect(page.getByLabel('段落 1 内部阅读提示',{exact:true})).toHaveValue('STAFF_GUIDE_0');
  expect(state.task!.document).toEqual(before);expect(state.writes).toHaveLength(0);
  if(platform==='wechat'){
   await watermark(page);
   await page.screenshot({path:'qa/screenshots/publication-wechat.png',fullPage:false});
  }
 });
}
test('copy action emits consumer text without headings and leaves history unchanged',async({page})=>{
 const t=makeTask();t.document!.paragraphs[0].heading='STAFF_ONLY_COPY';
 const before=structuredClone(t.document),state=await mockApi(page,t);
 await page.addInitScript(()=>{
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{(window as any).__copied=text;}}});
 });
 await page.goto('/');await page.getByRole('button',{name:'复制',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).__copied)).toBeTruthy();
 const copied=await page.evaluate(()=>(window as any).__copied);
 expect(copied).not.toContain('STAFF_ONLY_COPY');expect(copied).toContain(t.document!.title);
 expect(copied).toContain(t.document!.paragraphs[0].text);
 expect(state.task!.document).toEqual(before);expect(state.writes).toHaveLength(0);
});
