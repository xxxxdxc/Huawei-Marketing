import { test, expect, type Page } from '@playwright/test';
import { mockApi } from './fixtures';
import { plannerPreviewTask, previewPointPlan } from '../src/plannerPreviewData';

function fixture() { const task = plannerPreviewTask(); task.id = 'fixture-task'; return task; }
async function changeSelection(page: Page) {
  await page.getByRole('checkbox', { name: '选用卖点：围绕专注学习组织信息', exact: true }).uncheck();
  await page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true }).check();
}

test('selection is local until explicit update and cancel restores the current scope', async ({ page }) => {
  const state = await mockApi(page, fixture()); await page.goto('/');
  await expect(page.getByText('系统推荐', { exact: true })).toHaveCount(2);
  await expect(page.getByText('保留备选', { exact: true })).toHaveCount(1);
  await changeSelection(page);
  expect(state.writes).toHaveLength(0);
  expect(state.task!.plan!.selected_point_ids).toEqual(['C1', 'C2']);
  await expect(page.getByText('卖点选择已调整，大纲尚未更新', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '保存规划', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '撤销选用调整', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeEnabled();
  expect(state.writes).toHaveLength(0);
});

test('empty selection explains how to proceed and cannot update or confirm', async ({ page }) => {
  await mockApi(page, fixture()); await page.goto('/');
  await page.getByRole('checkbox', { name: '选用卖点：从课堂资料整理切入', exact: true }).uncheck();
  await page.getByRole('checkbox', { name: '选用卖点：围绕专注学习组织信息', exact: true }).uncheck();
  await expect(page.getByText('请至少选用一个有依据的卖点。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '按所选卖点更新大纲', exact: true })).toBeDisabled();
});

test('explicit update stays in planner while running and stops at second confirmation', async ({ page }) => {
  const state = await mockApi(page, fixture());
  const oldPlan = structuredClone(state.task!.plan!);
  await page.route('**/api/tasks/fixture-task/replan-points', async route => {
    const body = route.request().postDataJSON(); state.writes.push({ path: '/replan-points', body });
    expect(body).toEqual({ version: 1, selected_point_ids: ['C1', 'C3'], replace_current_plan: true });
    state.task!.status = 'planning'; state.task!.version++;
    setTimeout(() => { state.task!.plan = previewPointPlan(state.task!, body.selected_point_ids); state.task!.status = 'plan_ready'; state.task!.version++; }, 350);
    await route.fulfill({ status: 202, json: { accepted: true, task_id: 'fixture-task' } });
  });
  await page.goto('/'); await changeSelection(page);
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByText('正在更新大纲…', { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue(oldPlan.sections[0].heading);
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('1. 从课堂资料整理切入', { timeout: 10000 });
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeEnabled();
  expect(state.task!.plan!.selected_point_ids).toEqual(['C1', 'C3']);
  expect(state.task!.document).toBeNull();
  expect(state.writes).toHaveLength(1);
});

test('server refusal preserves selection and original outline with actionable reason', async ({ page }) => {
  const state = await mockApi(page, fixture());
  await page.route('**/api/tasks/fixture-task/replan-points', route => route.fulfill({ status: 400, json: { detail: '所选卖点未覆盖用户明确要求的内容，请保留课堂方向。' } }));
  await page.goto('/'); await changeSelection(page);
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByText('所选卖点未覆盖用户明确要求的内容，请保留课堂方向。', { exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true })).toBeChecked();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue(state.task!.plan!.sections[0].heading);
});

test('failed background update keeps unsaved edits and selection for retry', async ({ page }) => {
  const state = await mockApi(page, fixture());
  await page.route('**/api/tasks/fixture-task/replan-points', async route => {
    state.task!.status = 'planning'; state.task!.version++;
    setTimeout(() => { state.task!.status = 'plan_ready'; state.task!.error = '模拟：重规划失败，原大纲已保留'; state.task!.version++; }, 350);
    await route.fulfill({ status: 202, json: { accepted: true, task_id: 'fixture-task' } });
  });
  await page.goto('/'); await page.getByLabel('段落标题', { exact: true }).first().fill('未保存的手动标题');
  await changeSelection(page); page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByText('模拟：重规划失败，原大纲已保留', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('未保存的手动标题');
  await expect(page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true })).toBeChecked();
  await page.getByRole('button', { name: '撤销选用调整', exact: true }).click();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toBeEditable();
  await expect(page.getByRole('button', { name: '保存规划', exact: true })).toBeEnabled();
});

test('cancel replacing a manually edited plan sends no update', async ({ page }) => {
  const state = await mockApi(page, fixture()); await page.goto('/');
  await page.getByLabel('段落标题', { exact: true }).first().fill('保留这段手动编辑'); await changeSelection(page);
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  expect(state.writes).toHaveLength(0);
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('保留这段手动编辑');
});

test('stale replan version keeps draft and requires explicit reload', async ({ page }) => {
  await mockApi(page, fixture()); await page.route('**/api/tasks/fixture-task/replan-points', route => route.fulfill({ status: 409, json: { detail: '任务已更新' } }));
  await page.goto('/'); await changeSelection(page);
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新载入最新版本', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '选用卖点：回应小组展示准备需求', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: '按所选卖点更新大纲', exact: true })).toBeDisabled();
});

test('local demonstration rebuilds only after click and retains old versions', async ({ page }) => {
  let writes = 0; page.on('request', request => { if (request.url().includes('/api/') && request.method() !== 'GET') writes++; });
  await page.goto('/?preview=planner-v2'); await changeSelection(page);
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByText('演示大纲已按所选卖点更新，旧版本已保留。还没有开始写稿。', { exact: true })).toBeVisible();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('1. 从课堂资料整理切入');
  await page.getByText('演示版本记录 · 1 个旧版本', { exact: true }).click();
  await page.getByRole('button', { name: '恢复此演示版本', exact: true }).click();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('从一天的课堂开始');
  expect(writes).toBe(0);
});

test('Moments recommends one point but permits an explicit broader selection', async ({ page }) => {
  await page.goto('/?preview=planner-v2&platform=moments');
  await expect(page.getByRole('checkbox', { name: /^选用卖点：/ }).and(page.locator(':checked'))).toHaveCount(1);
  await page.getByRole('checkbox', { name: '选用卖点：围绕专注学习组织信息', exact: true }).check();
  await expect(page.getByRole('button', { name: '按所选卖点更新大纲', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '按所选卖点更新大纲', exact: true }).click();
  await expect(page.getByText('当前大纲采用 2 个卖点', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeEnabled();
});
