import {test,expect} from '@playwright/test';
import {makeTask,mockApi,watermark} from './fixtures';
import {imageLayout,sequenceImages} from '../src/contentLayout';
function task(status='approved',platform='xiaohongshu'){
 const t=makeTask(status,platform),p=t.plan!;
 p.schema_version='2';p.product_id=t.product_id!;p.narrative={framework:'problem_solution',reason:'根据测试受众的问题逐步展开',ordering_rationale:'先问题再依据'};p.selected_point_ids=['C1'];
 p.sections=sequenceImages(p.sections.map((s,i)=>({...s,reader_question:`测试问题${i+1}`,role:'argument' as const,point_ids:['C1'],target_chars:100})),platform);
 p.planning_analysis={status:'generated',candidates:[{id:'C1',direction:'模拟卖点',audience_need:'模拟需求',fact_ids:['fact-1'],image_ids:['fixture-image-1'],conditions:['模拟条件'],scores:Object.fromEntries(['audience','evidence','differentiation','image'].map(k=>[k,{value:3,reason:'模拟评分'}])) as any,total_score:75,rank:1}],warnings:[]};return t;
}
test('V2 gallery uses explicit order and document override',()=>{const t=task();t.plan!.sections[0].image_position!.order=3;t.plan!.sections[2].image_position!.order=1;t.document!.paragraphs[2].image_id='override';expect(imageLayout(t.plan,'xiaohongshu',t.document!)[0].image_id).toBe('override');});
test('legacy positions derive reading order',()=>{const t=makeTask();expect(imageLayout(t.plan,'xiaohongshu').map(s=>s.order)).toEqual([1,2,3]);});
test('resequence repairs removal',()=>{const t=task();expect(sequenceImages(t.plan!.sections.slice(1),'xiaohongshu').map(s=>s.image_position.order)).toEqual([1,2]);});
test('V2 planning controls persist positions and show stale warning',async({page})=>{
 const state=await mockApi(page,task('plan_ready','wechat'));await page.goto('/');await expect(page.getByLabel('叙事框架',{exact:true})).toHaveCount(0);await expect(page.getByText('为什么这样编排',{exact:true})).toBeVisible();
 await page.getByLabel('读者问题',{exact:true}).first().fill('我需要核实什么？');await page.getByLabel('图片插入位置',{exact:true}).first().selectOption('before_section');
 await page.getByText('查看生成时的卖点排序与依据',{exact:true}).click();await expect(page.getByText('规划已修改，以下评分仅为生成时记录，不代表当前规划的最新评价。')).toBeVisible();
 await page.getByRole('button',{name:'保存规划',exact:true}).click();expect(state.task!.plan!.sections[0].image_position!.kind).toBe('before_section');expect(state.task!.plan!.sections[0].reader_question).toBe('我需要核实什么？');
});
test('WeChat preview places before/after figures correctly',async({page})=>{
 const t=task('approved','wechat');t.plan!.sections[0].image_position={kind:'before_section',order:null};await mockApi(page,t);await page.goto('/');
 const sections=page.locator('.wechat-article > section');expect(await sections.nth(0).evaluate(e=>e.firstElementChild?.tagName)).toBe('FIGURE');expect(await sections.nth(1).evaluate(e=>e.lastElementChild?.tagName)).toBe('FIGURE');await watermark(page);await page.screenshot({path:'qa/screenshots/planner-v2-wechat.png',fullPage:false});
});
test('Xiaohongshu preview uses chosen cover and ordered carousel',async({page})=>{
 const t=task();t.plan!.sections[0].image_position!.order=3;t.plan!.sections[2].image_position!.order=1;await mockApi(page,t);await page.goto('/');await expect(page.locator('.preview-carousel img')).toHaveAttribute('src','/api/assets/fixture-image-3');await page.getByRole('button',{name:'下一张预览图片'}).click();await expect(page.locator('.preview-carousel img')).toHaveAttribute('src','/api/assets/fixture-image-2');
});
test('Moments grid follows explicit order',async({page})=>{const t=task('approved','moments');t.plan!.sections[0].image_position!.order=3;t.plan!.sections[2].image_position!.order=1;await mockApi(page,t);await page.goto('/');await expect(page.locator('.moments-grid img').first()).toHaveAttribute('src','/api/assets/fixture-image-3');});
