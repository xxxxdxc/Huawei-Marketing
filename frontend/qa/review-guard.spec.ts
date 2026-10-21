import { test, expect } from '@playwright/test';
import { makeTask, mockApi } from './fixtures';

test('unbound scope opinion is shown as reviewer recheck, not a product violation', async ({ page }) => {
  const task=makeTask('needs_review','wechat');
  task.review!.issues=[];
  task.review!.summary='核验意见与实际舍弃范围不一致，原稿与配图已保留。';
  task.review!.validation_errors=['核验意见1：所指主题不在用户实际舍弃范围内，请重新核验。'];
  task.review!.scope_audit=[{accepted:false,reasons:['图表不属于实际舍弃的续航主题'],original_issue:{category:'image',location:'第三段配图',detail:'图表触及已舍弃主题，应换图',severity:'error',repairable:true}}];
  const state=await mockApi(page,task);
  await page.goto('/');await page.getByRole('button',{name:'核验',exact:true}).click();
  await expect(page.getByRole('heading',{name:'核验意见需要复核',exact:true})).toBeVisible();
  await expect(page.locator('.review-issue')).toHaveCount(0);
  await expect(page.locator('.review-panel')).toContainText('无需重新选卖点或写稿');
  await page.getByText('查看未采纳的核验意见',{exact:true}).click();
  await expect(page.locator('.review-panel')).toContainText('图表不属于实际舍弃的续航主题');
  await expect(page.getByRole('button',{name:'公众号排版与复制',exact:true})).toBeDisabled();
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button',{name:'重新核验',exact:true}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes[0].path).toMatch(/\/review$/);
});

test('image issue explicitly routes to image editing and retains the document', async ({page})=>{
 const task=makeTask('needs_review');
 task.review!.issues=[{category:'image',location:'第三段配图',detail:'该画面与当前型号不符，请核对',severity:'error',repairable:false}];
 const original=structuredClone(task.document),state=await mockApi(page,task);
 await page.goto('/');await page.getByRole('button',{name:'核验',exact:true}).click();
 await expect(page.locator('.review-issue')).toContainText('文字修订不会自动换图');
 expect(state.task!.document).toEqual(original);expect(state.writes).toHaveLength(0);
});

test('failed text repair still exposes initial review issues',async({page})=>{
 const task=makeTask('error','wechat');task.resume_status='needs_review';
 task.error='自动文字修订未完成，原稿和首次核验报告已保留';
 task.review=makeTask('needs_review','wechat').review;
 task.review!.summary='首次核验发现一处表达问题';
 await mockApi(page,task);await page.goto('/');
 await page.getByRole('button',{name:'核验',exact:true}).click();
 await expect(page.locator('.review-panel')).toContainText('首次核验发现一处表达问题');
 await expect(page.locator('.review-issue')).toHaveCount(1);
});
