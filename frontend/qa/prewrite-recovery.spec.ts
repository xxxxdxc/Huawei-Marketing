import { test, expect } from '@playwright/test';
import { makeV2Task, mockApi } from './fixtures';
import { selectionPreviewTask } from '../src/selectionPreviewData';
for (const [stage,label] of [['source_retrieval','资料读取'],['fact_extraction','事实提取'],['image_review','图片核验'],['selling_points','卖点生成']] as const) {
 test(`${stage} exposes current-step retry instead of Brief reanalysis`, async ({page})=>{
  const task=makeV2Task(true);task.status='error';task.resume_status='brief_ready';task.plan=null;task.document=null;task.review=null;
  task.error='模型网关或上游服务暂时未完成响应（HTTP 524）';task.prewrite_recovery={stage,label,resumable:true};
  const state=await mockApi(page,task);const calls:unknown[]=[];
  await page.route('**/api/tasks/fixture-task/retry-prewrite',async route=>{
   calls.push(route.request().postDataJSON());const next=selectionPreviewTask();next.id='fixture-task';next.version=task.version+1;state.task=next;
   await route.fulfill({status:202,json:{accepted:true}});
  });
  await page.goto('/');await expect(page.getByText(`${label}已暂停`,{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'重新分析需求',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:`重试${label}`,exact:true}).click();
  await expect(page.getByRole('button',{name:'确认卖点，开始写稿',exact:true})).toBeEnabled();
  expect(calls).toEqual([{version:10}]);expect(state.writes).toHaveLength(0);
 });
}
test('changed checkpoint blocks retry of stale inputs',async({page})=>{
 const task=makeV2Task(true);task.status='error';task.resume_status='brief_ready';task.plan=null;task.document=null;task.error='HTTP 524';
 task.prewrite_recovery={stage:'image_review',label:'图片核验',resumable:false,reason:'需求、资料或取舍已变化，不能沿用这个检查点。'};
 const state=await mockApi(page,task);await page.goto('/');
 await expect(page.getByRole('button',{name:'重试图片核验',exact:true})).toBeDisabled();
 await expect(page.getByText(task.prewrite_recovery.reason!,{exact:true})).toBeVisible();expect(state.writes).toHaveLength(0);
});
