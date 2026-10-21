import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { makeTask, makeV2Task, mockApi, watermark } from './fixtures';
import type { ReviewOverview, ResolutionPreview } from '../src/evidenceResolutionTypes';

async function setup(page:Page, options:{ack?:boolean;block?:boolean;protected?:boolean;preview409?:boolean;ima?:boolean;overviewFailure?:boolean}={}) {
  const task=makeV2Task(true); task.status='needs_review';task.resume_status='needs_review';task.error='模拟：关键续航依据缺失';task.package=makeTask('plan_ready').package;task.plan=null;task.document=null;task.review=null;
  const request={id:'r1',direction_id:'d1',question:'续航是否满足课程需求？',priority:'required'};
  const keep={id:'r2',direction_id:'d2',question:'重量是否有依据？',priority:'required'};
  const linked={id:'r3',direction_id:'d3',question:'是否兼顾轻便与续航？',priority:'required'};
  task.brief_analysis!.retrieval_plan!.facts=[request,keep,linked];
  task.brief_analysis!.message_strategy!.priorities=[{id:'d1',direction:'续航表现',reason:'模拟'},{id:'d2',direction:'轻便',reason:'模拟'},{id:'d3',direction:'轻便与续航兼顾',reason:'模拟'}];
  task.package!.coverage=[{request_id:'r1',status:'not_found',fact_ids:[],reason:'没有续航时长及测试条件'},{request_id:'r2',status:'supported',fact_ids:['fact-1'],reason:'有重量依据'}];
  const blocked={code:'missing',reason:'续航缺少官方测试条件',request_id:'r1',waivable:!options.protected};
  const summary:ReviewOverview={version:10,knowledge_source:options.ima?'ima':'local_zip',local_archive_path:options.ima?null:'D:/fixtures/knowledge.zip',actions:['adjust_content','refresh_evidence','modify_requirements'],task_upload_supported:false,unmet_requirements:[{request,coverage:task.package!.coverage[0],found:[],missing:'没有续航时长及测试条件',affected_direction_ids:['d1','d3'],blocking:true,omitted:false,can_drop:!options.protected,non_waivable_reason:options.protected?'必要兼容条件不能跳过':null}],available_facts:task.package!.facts,blockers:[blocked],material_requirements:[{request_id:'r1',question:request.question,target_model:'测试型号',conditions:['同一配置及测试场景'],document_types:['官方续航测试说明']}]};
  const preview:ResolutionPreview={task_id:task.id,version:10,preview_id:'preview-test-10',selected_request_ids:['r1'],selected_direction_ids:[],removed:[{request,coverage:task.package!.coverage[0]},{request:linked,coverage:null}],affected_directions:[{direction:{id:'d3',direction:'轻便与续航兼顾'},request_ids:['r3'],reason:'依赖续航证据'}],retained:[{request:keep,coverage:task.package!.coverage[1]}],retained_fact_ids:['fact-1'],excluded_fact_ids:[],excluded_image_ids:['fixture-image-4'],remaining_blockers:options.block?[{code:'image_shortage',reason:'现有图片不足，请补充图片',waivable:false}]:[],required_constraint_acks:options.ack?[{id:'c1',request_id:'r1',description:'本次不写续航',requires_ack:true,evidence:[{turn_id:'u1',quote:'没有续航数据就不生成'}]}]:[],prohibited_topic_labels:['续航表现'],can_apply:!options.block,requires_asset_review:false};
  const state=await mockApi(page,task);
  const local={summary,preview,calls:[] as {path:string;body:any}[],preview409:!!options.preview409,overviewFailure:!!options.overviewFailure,confirmFailure:0,refreshPaused:false};
  await page.route('**/api/tasks/fixture-task/evidence-review',route=>route.fulfill({status:local.overviewFailure?503:200,contentType:'application/json',body:JSON.stringify(local.overviewFailure?{detail:'模拟：审查概览暂不可用'}:local.summary)}));
  await page.route('**/api/tasks/fixture-task/evidence-resolution/*',async route=>{
    const path=new URL(route.request().url()).pathname;const body=route.request().postDataJSON();local.calls.push({path,body});
    if(path.endsWith('/preview'))return route.fulfill({status:local.preview409?409:200,contentType:'application/json',body:JSON.stringify(local.preview409?{detail:'预览版本已过期'}:local.preview)});
    if(local.confirmFailure)return route.fulfill({status:local.confirmFailure,contentType:'application/json',body:JSON.stringify({detail:'模拟：确认失败'})});
    state.task={...makeTask('plan_ready'),version:11,execution_scope:{omitted_request_ids:['r1','r3'],omitted_direction_ids:['d1','d3']}};
    return route.fulfill({status:202,contentType:'application/json',body:'{"accepted":true}'});
  });
  await page.route('**/api/tasks/fixture-task/refresh-evidence',async route=>{
    local.calls.push({path:new URL(route.request().url()).pathname,body:route.request().postDataJSON()});
    state.task=local.refreshPaused?{...task,version:11}: {...makeTask('plan_ready'),version:11};local.summary={...summary,version:11};
    return route.fulfill({status:202,contentType:'application/json',body:'{"accepted":true}'});
  });
  await page.goto('/');await expect(page.getByRole('heading',{name:'尚未满足的需求'})).toBeVisible();
  return {state,local};
}
async function selectAndPreview(page:Page){await page.getByLabel('本次不写这项内容',{exact:true}).check();await page.getByRole('button',{name:'查看取舍影响'}).click();await expect(page.getByRole('heading',{name:'确认本次内容调整'})).toBeVisible();}

test('resolution preview is read only; dependency impact visible; explicit confirmation stops at planner',async({page})=>{
 const {local,state}=await setup(page);expect(local.calls).toHaveLength(0);
 await selectAndPreview(page);expect(local.calls).toHaveLength(1);expect(state.task!.version).toBe(10);
 await expect(page.getByText('关联影响',{exact:true})).toBeVisible();await expect(page.locator('.resolution-preview')).toContainText('重量是否有依据');
 await page.getByRole('button',{name:'确认调整，继续规划'}).click();await expect(page.getByRole('button',{name:'确认规划，开始写稿'})).toBeVisible();
 expect(local.calls[1].body).toEqual({version:10,preview_id:'preview-test-10',drop_request_ids:['r1'],drop_direction_ids:[],confirmed:true,acknowledged_constraint_ids:[]});
 expect(state.writes.some(w=>w.path.endsWith('/confirm-plan'))).toBeFalsy();
});

test('constraint relaxation needs unchecked explicit consent; cancel sends nothing',async({page})=>{
 const {local}=await setup(page,{ack:true});await selectAndPreview(page);
 await expect(page.getByText('你原来的要求：“没有续航数据就不生成”')).toBeVisible();
 await expect(page.getByRole('button',{name:'确认调整，继续规划'})).toBeDisabled();
 await page.getByRole('button',{name:'取消确认'}).click();expect(local.calls).toHaveLength(1);
 await selectAndPreview(page);await page.getByLabel('我同意本次放宽此要求：本次不写续航').check();
 await page.getByRole('button',{name:'确认调整，继续规划'}).click();expect(local.calls.at(-1)!.body.acknowledged_constraint_ids).toEqual(['c1']);
});

test('remaining blockers forbid applying preview and protected requirements cannot be dropped',async({page})=>{
 const {local}=await setup(page,{block:true});await selectAndPreview(page);
 await expect(page.getByText('现有图片不足，请补充图片')).toBeVisible();await expect(page.getByRole('button',{name:'确认调整，继续规划'})).toBeDisabled();expect(local.calls).toHaveLength(1);
});
test('protected requirement offers material and whole requirement paths',async({page})=>{
 await setup(page,{protected:true});await expect(page.getByLabel(/本次不写这项内容/)).toBeDisabled();
 await expect(page.getByText('必要兼容条件不能跳过')).toBeVisible();await expect(page.getByRole('button',{name:'补充依据，再检查'})).toBeEnabled();
});

test('expired preview locks actions and reload preserves explicit discard guard',async({page})=>{
 const {local}=await setup(page,{preview409:true});await page.getByLabel('本次不写这项内容',{exact:true}).check();await page.getByRole('button',{name:'查看取舍影响'}).click();
 await expect(page.getByText('任务已更新。请重新载入最新版本，再继续编辑。当前未保存内容仍保留在页面中。')).toBeVisible();await expect(page.getByRole('button',{name:'查看取舍影响'})).toBeDisabled();expect(local.calls).toHaveLength(1);
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'重新载入最新版本'}).click();await expect(page.getByLabel('本次不写这项内容',{exact:true})).not.toBeChecked();
});

test('changing selection invalidates preview; failed confirm preserves selection and requires new preview',async({page})=>{
 const {local}=await setup(page);await selectAndPreview(page);await page.getByLabel('本次不写这项内容',{exact:true}).uncheck();await expect(page.getByRole('button',{name:'确认调整，继续规划'})).toHaveCount(0);
 await selectAndPreview(page);local.confirmFailure=500;await page.getByRole('button',{name:'确认调整，继续规划'}).click();
 await expect(page.getByLabel('本次不写这项内容',{exact:true})).toBeChecked();await expect(page.getByRole('button',{name:'确认调整，继续规划'})).toHaveCount(0);
});

for(const ima of [false,true])test(`refresh uses actual source and explicit update acknowledgment: ${ima}`,async({page})=>{
 const {local}=await setup(page,{ima});await page.getByRole('button',{name:'补充依据，再检查'}).click();
 await expect(page.locator('.resolution-preview')).toContainText(ima?'ima 知识库':'D:/fixtures/knowledge.zip');await expect(page.getByText('需要：官方续航测试说明')).toBeVisible();
 await expect(page.getByRole('button',{name:'资料已更新，重新检查'})).toBeDisabled();expect(local.calls).toHaveLength(0);
 await page.getByLabel('我已更新原资料源，重新读取并检查').check();local.refreshPaused=true;await page.getByRole('button',{name:'资料已更新，重新检查'}).click();
 await expect(page.getByRole('heading',{name:'先处理这些缺口，再继续规划'})).toBeVisible();expect(local.calls[0].body).toEqual({version:10});await expect(page.getByRole('button',{name:'查看取舍影响'})).toBeVisible();
});

test('whole requirement change has clear reset and returns to strategy confirmation',async({page})=>{
 const {state}=await setup(page);await page.getByRole('button',{name:'重新描述需求',exact:true}).click();await page.getByLabel('调整后的需求').fill('仅介绍轻便，重新分析学生的需求');
 await expect(page.getByRole('button',{name:'提交需求，重新分析'})).toBeDisabled();await page.getByLabel('确认按新需求重新分析').check();await page.getByRole('button',{name:'提交需求，重新分析'}).click();
 await expect(page.getByRole('button',{name:'确认策略，查资料'})).toBeVisible();expect(state.writes.at(-1)!.path).toContain('/modify');
});

test('overview failure is retriable without authorizing mutation',async({page})=>{
 const task=makeV2Task(true);task.status='needs_review';task.package=makeTask('plan_ready').package;task.package!.coverage=[];
 await mockApi(page,task);let fails=true;await page.route('**/evidence-review',r=>r.fulfill({status:fails?503:200,contentType:'application/json',body:JSON.stringify(fails?{detail:'服务暂不可用'}:{version:10,knowledge_source:'ima',unmet_requirements:[],available_facts:[],blockers:[],material_requirements:[],actions:[]})}));await page.goto('/');
 await expect(page.getByText('服务暂不可用')).toBeVisible();fails=false;await page.getByRole('button',{name:'重新读取审查结果'}).click();await expect(page.getByText('当前没有可调整的缺证项，请按上方门槛补充依据或重新描述需求。')).toBeVisible();
});

test('review resolution keyboard accessibility and responsive layout',async({page})=>{
 await setup(page,{ack:true});await selectAndPreview(page);
 await expect(page.getByRole('heading',{name:'确认本次内容调整'})).toBeFocused();
 let report=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();expect(report.violations).toEqual([]);
 await watermark(page);await page.locator('.evidence-resolution').screenshot({path:'qa/screenshots/evidence-resolution-desktop.png'});
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.locator('.evidence-resolution').screenshot({path:'qa/screenshots/evidence-resolution-mobile.png'});
 report=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();expect(report.violations).toEqual([]);
});


test('adjust content button opens read-only preview for checked omissions',async({page})=>{
 const {local,state}=await setup(page,{ack:true});
 await page.getByLabel('本次不写这项内容',{exact:true}).check();
 await page.getByRole('button',{name:'调整内容，继续创作',exact:true}).click();
 await expect(page.getByRole('heading',{name:'确认本次内容调整'})).toBeVisible();
 expect(local.calls).toHaveLength(1);
 expect(local.calls[0].path).toContain('/evidence-resolution/preview');
 expect(local.calls[0].body).toEqual({version:10,drop_request_ids:['r1'],drop_direction_ids:[]});
 expect(state.task!.version).toBe(10);
 await expect(page.getByRole('button',{name:'确认调整，继续规划'})).toBeDisabled();
 await page.getByLabel('我同意本次放宽此要求：本次不写续航').check();
 await page.getByRole('button',{name:'确认调整，继续规划'}).click();
 await expect(page.getByRole('button',{name:'确认规划，开始写稿'})).toBeVisible();
 expect(local.calls).toHaveLength(2);
 expect(state.writes.some(w=>w.path.endsWith('/confirm-plan'))).toBeFalsy();
});

test('adjust content button explains missing selection without sending a request',async({page})=>{
 const {local}=await setup(page);
 await page.getByRole('button',{name:'调整内容，继续创作',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'请先勾选本次不写的内容，再查看取舍影响。'})).toBeVisible();
 expect(local.calls).toHaveLength(0);
});
