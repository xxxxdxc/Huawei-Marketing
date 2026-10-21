import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mockApi } from './fixtures';
import { selectionPreviewTask, selectionPreviewComposition, selectionPreviewDocument } from '../src/selectionPreviewData';

function selected() { const task = selectionPreviewTask(); task.id = 'fixture-task'; return task; }
function composed() { const task = selected(); task.selection_confirmation = { selection_hash: 'fixture-selection', authorized_version: 1, at: '2026-10-21T00:00:00Z' }; return selectionPreviewDocument(selectionPreviewComposition(task, task.plan!.selected_point_ids!)); }
async function chooseDifferentPoints(page: Page) {
  await page.getByRole('checkbox', { name: '选用卖点：围绕专注学习组织信息', exact: true }).uncheck();
  await page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true }).check();
}

test('V3 second confirmation selects points without any outline or image-budget gate', async ({ page }) => {
  const state = await mockApi(page, selected()); await page.goto('/');
  await expect(page.getByRole('heading', { name: '先确定这篇要讲什么', exact: true })).toBeVisible();
  await expect(page.locator('.plan-card')).toHaveCount(0);
  await expect(page.getByLabel('段落篇幅预算（字）', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('叙事框架', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toBeEnabled();
  expect(state.task!.plan!.sections).toEqual([]);
});

test('V3 optional saving only persists selection without entering model stages', async ({ page }) => {
  const state = await mockApi(page, selected());
  await page.route('**/api/tasks/fixture-task/replan-points', async route => {
    const body = route.request().postDataJSON(); state.writes.push({ path: '/replan-points', body });
    expect(body.replace_current_plan).toBe(true);
    state.task!.plan!.selected_point_ids = body.selected_point_ids; state.task!.version++;
    await route.fulfill({ json: { accepted: true, task_id: 'fixture-task' } });
  });
  await page.goto('/'); await chooseDifferentPoints(page);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '保存卖点选择', exact: true }).click();
  expect(state.task!.plan!.selected_point_ids).toEqual(['C1', 'C3']);
  expect(state.task!.status).toBe('plan_ready'); expect(state.task!.plan!.phase).toBe('selection');
  expect(state.task!.plan!.sections).toEqual([]); expect(state.task!.writer_outline).toBeUndefined();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toBeEnabled();
  expect(state.writes).toHaveLength(1);
});

test('V3 direct confirmation submits local points and automatically runs both Writer stages', async ({ page }) => {
  const state = await mockApi(page, selected());
  await page.route('**/api/tasks/fixture-task/confirm-plan', async route => {
    const body = route.request().postDataJSON(); state.writes.push({ path: '/confirm-plan', body });
    expect(body.plan.selected_point_ids).toEqual(['C1', 'C3']);
    state.task!.plan!.selected_point_ids = body.plan.selected_point_ids;
    state.task!.selection_confirmation = { selection_hash: 'fixture-confirmed', authorized_version: 2, at: '2026-10-21T00:00:00Z' };
    state.task!.status = 'writing'; state.task!.writer_stage = 'outlining'; state.task!.version++;
    setTimeout(() => { state.task = { ...selectionPreviewComposition(state.task!, body.plan.selected_point_ids), version: state.task!.version + 1 }; }, 2200);
    setTimeout(() => { state.task = { ...selectionPreviewDocument(state.task!), version: state.task!.version + 1 }; }, 4600);
    await route.fulfill({ status: 202, json: { accepted: true, task_id: 'fixture-task' } });
  });
  await page.goto('/'); await chooseDifferentPoints(page);
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toBeEnabled();
  await page.getByRole('button', { name: '确认卖点，开始写稿' }).click();
  await expect(page.getByRole('heading', { name: '正在安排结构与配图' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '正在生成正文' })).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel('标题', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole('button', { name: '确认大纲' })).toHaveCount(0);
  expect(state.writes.map(write => write.path)).toEqual(['/confirm-plan']);
});

test('V3 empty selection blocks saving and confirmation with a useful message', async ({ page }) => {
  await mockApi(page, selected()); await page.goto('/');
  await page.getByRole('checkbox', { name: '选用卖点：从课堂资料整理切入', exact: true }).uncheck();
  await page.getByRole('checkbox', { name: '选用卖点：围绕专注学习组织信息', exact: true }).uncheck();
  await expect(page.getByText('请先选用 1–8 个候选卖点。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '保存卖点选择' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toBeDisabled();
});

test('V3 failed save or confirmation keeps the local choice', async ({ page }) => {
  await mockApi(page, selected());
  await page.route('**/api/tasks/fixture-task/replan-points', route => route.fulfill({ status: 400, json: { detail: '模拟：必须内容尚未覆盖，请调整选择。' } }));
  await page.route('**/api/tasks/fixture-task/confirm-plan', route => route.fulfill({ status: 400, json: { detail: '模拟：确认未通过，请保留必要卖点。' } }));
  await page.goto('/'); await chooseDifferentPoints(page);
  await page.getByRole('button', { name: '保存卖点选择' }).click();
  await expect(page.getByText('模拟：必须内容尚未覆盖，请调整选择。', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认卖点，开始写稿' }).click();
  await expect(page.getByText('模拟：确认未通过，请保留必要卖点。', { exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true })).toBeChecked();
});

test('V3 version conflict locks actions without discarding selection', async ({ page }) => {
  await mockApi(page, selected());
  await page.route('**/api/tasks/fixture-task/confirm-plan', route => route.fulfill({ status: 409, json: { detail: '任务已更新' } }));
  await page.goto('/'); await chooseDifferentPoints(page);
  await page.getByRole('button', { name: '确认卖点，开始写稿' }).click();
  await expect(page.getByRole('button', { name: '重新载入最新版本', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toBeDisabled();
});

test('V3 drafting failure retains an operable retry even after structure composition', async ({ page }) => {
  const task = composed(); task.document = null; task.review = null; task.status = 'error'; task.resume_status = 'plan_ready'; task.writer_stage = 'drafting'; task.error = '模拟：正文生成失败，结构已保留';
  const state = await mockApi(page, task);
  await page.route('**/api/tasks/fixture-task/confirm-plan', async route => { state.writes.push({ path: '/confirm-plan', body: route.request().postDataJSON() }); await route.fulfill({ status: 400, json: { detail: '模拟重试，不调用模型' } }); });
  await page.goto('/'); await expect(page.getByRole('button', { name: '重试编排并写稿', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '重试编排并写稿', exact: true }).click();
  expect(state.writes[0].body.plan.selected_point_ids).toEqual(['C1', 'C2']);
  await expect(page.locator('.plan-card')).toHaveCount(0);
});

test('V3 composed plan is a readonly selection record and Writer structure is optional', async ({ page }) => {
  await mockApi(page, composed()); await page.goto('/');
  await page.getByText('查看自动编排记录', { exact: true }).click();
  await expect(page.getByText('内容主线：', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('与上一段衔接：承接上一段的问题，补充下一步需要了解的信息。', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '核心卖点', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: /^选用卖点：/ }).first()).toBeDisabled();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toHaveCount(0);
});

test('V3 platform switch keeps confirmed points and directly restarts Writer', async ({ page }) => {
  const state = await mockApi(page, composed());
  await page.route('**/api/tasks/fixture-task/change-platform', async route => {
    const body = route.request().postDataJSON(); state.writes.push({ path: '/change-platform', body });
    state.task!.platform = body.platform; state.task!.brief!.platform = body.platform;
    state.task!.document = null; state.task!.review = null; state.task!.status = 'writing'; state.task!.writer_stage = 'outlining'; state.task!.version++;
    await route.fulfill({ status: 202, json: { accepted: true, task_id: 'fixture-task' } });
  });
  await page.goto('/'); await page.getByRole('button', { name: '更换目标平台', exact: true }).click();
  await page.getByLabel('新目标平台').selectOption('moments');
  await expect(page.getByRole('button', { name: '更换平台并重新写稿', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '更换平台并重新写稿', exact: true }).click();
  await expect(page.getByRole('heading', { name: '正在安排结构与配图' })).toBeVisible();
  expect(state.task!.plan!.selected_point_ids).toEqual(['C1', 'C2']);
  expect(state.writes.at(-1)?.path).toBe('/change-platform');
});

for (const width of [1440, 390]) test(`V3 selection preview is accessible and responsive at ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1050 });
  await page.goto('/?preview=planner-v3');
  await expect(page.getByRole('heading', { name: '先确定这篇要讲什么', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `qa/screenshots/planner-v3-selection-${width}.png`, fullPage: false });
});

test('V3 local preview completes two stages with no API write or third confirmation', async ({ page }) => {
  let writes = 0; page.on('request', request => { if (request.url().includes('/api/') && request.method() !== 'GET') writes++; });
  await page.goto('/?preview=planner-v3'); await chooseDifferentPoints(page);
  await page.getByRole('button', { name: '确认卖点，开始写稿' }).click();
  await expect(page.getByLabel('标题', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认大纲' })).toHaveCount(0);
  await page.getByText('查看自动编排记录', { exact: true }).click();
  await expect(page.getByText('内容主线：', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  expect(writes).toBe(0);
  await page.screenshot({ path: 'qa/screenshots/planner-v3-draft.png', fullPage: false });
});
