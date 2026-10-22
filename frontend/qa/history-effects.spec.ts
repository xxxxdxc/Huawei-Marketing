import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { makeTask, mockApi } from './fixtures';
import { CASE_STORAGE_KEY } from '../src/historyEffectsData';

async function openDemo(page: Page) { await page.goto('/?preview=history-effects'); await expect(page.getByRole('heading',{name:'历史任务',exact:true})).toBeVisible(); }
async function openCampus(page: Page, platform='小红书') { await page.getByRole('button',{name:`查看${platform}图文与效果：开学购机`,exact:true}).click(); await expect(page.getByRole('dialog',{name:'推文与效果',exact:true})).toBeVisible(); }
async function addCase(page: Page) { await page.getByRole('dialog').getByRole('button',{name:'加入优秀案例库',exact:true}).click(); await expect(page.getByRole('heading',{name:'已加入演示案例库',exact:true})).toBeVisible(); }
async function closeDialog(page: Page) { await page.getByRole('dialog').getByRole('button',{name:'关闭面板',exact:true}).click(); }

test('real history stays separate from simulated metrics and still opens the original task', async ({page})=>{
 const state=await mockApi(page,makeTask());await page.goto('/');
 await page.getByRole('button',{name:/^历史任务/}).click();
 await expect(page.getByRole('button',{name:'任务记录 1',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('已核验记录',{exact:true})).toBeVisible();
 await expect(page.getByText('3,280',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'效果演示 功能原型',exact:true}).click();await openCampus(page);await addCase(page);await closeDialog(page);
 await page.getByRole('button',{name:'任务记录 1',exact:true}).click();
 await page.locator('.task-table>button').click();await expect(page.getByLabel('标题',{exact:true})).toBeVisible();
 expect(state.task!.id).toBe('fixture-task');expect(state.writes).toHaveLength(0);
});

test('three demo campaigns have real actions, explicit mock provenance and no API requests',async({page})=>{
 const requests:string[]=[];page.on('request',request=>{if(request.url().includes('/api/'))requests.push(request.url());});
 await openDemo(page);await expect(page.locator('.history-campaign')).toHaveCount(3);await expect(page.locator('.history-publication')).toHaveCount(9);
 await expect(page.getByText('3,280',{exact:true})).toBeVisible();await expect(page.getByText('效果与经验学习 · 前端演示',{exact:true})).toBeVisible();
 await openCampus(page,'门店朋友圈');await expect(page.getByRole('dialog')).toContainText('未实际发布，无真实推文链接');
 await expect(page.getByRole('dialog').locator('.history-post-metrics dd[aria-label]')).toHaveCount(2);
 await expect(page.getByRole('dialog').locator('a[href^="http"]')).toHaveCount(0);
 expect(requests).toEqual([]);
});

test('each platform presents its own full content layout and images',async({page})=>{
 await openDemo(page);await openCampus(page);
 await expect(page.locator('.preview-xiaohongshu.history-post-preview')).toBeVisible();
 await page.getByRole('button',{name:'下一张示意图片',exact:true}).click();await expect(page.getByText('2 / 3',{exact:true})).toBeVisible();await closeDialog(page);
 await openCampus(page,'微信公众号');await expect(page.locator('.wechat-article.history-post-preview')).toBeVisible();await expect(page.locator('.history-post-preview figure')).toHaveCount(2);await closeDialog(page);
 await openCampus(page,'门店朋友圈');await expect(page.locator('.moments-post.history-post-preview')).toBeVisible();
});

test('manual selection shows a simulated analysis, persists once and filters excellent cases',async({page})=>{
 await openDemo(page);await page.getByRole('button',{name:/^优秀案例/}).click();await expect(page.getByRole('heading',{name:'还没有符合筛选的优秀案例',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'浏览全部样例',exact:true}).click();await openCampus(page);await addCase(page);
 await expect(page.getByRole('dialog')).toContainText('正文结构');await expect(page.getByRole('dialog')).toContainText('案例尚未接入真实 Writer References');
 expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)!).ids,CASE_STORAGE_KEY)).toEqual(['demo-history-campus-xiaohongshu']);
 await closeDialog(page);await page.getByRole('button',{name:/^优秀案例/}).click();await expect(page.locator('.history-publication')).toHaveCount(1);
 await page.reload();await page.getByRole('button',{name:/^优秀案例/}).click();await expect(page.locator('.history-publication')).toHaveCount(1);
});

test('closing a simulated extraction cancels it instead of silently adding a case',async({page})=>{
 await openDemo(page);await openCampus(page);await page.getByRole('button',{name:'加入优秀案例库',exact:true}).click();
 await expect(page.getByRole('button',{name:'正在模拟提炼…',exact:true})).toBeDisabled();await page.keyboard.press('Escape');
 await page.waitForTimeout(800);
 expect(await page.evaluate(key=>localStorage.getItem(key),CASE_STORAGE_KEY)).toBeNull();
 await page.getByRole('button',{name:/^优秀案例/}).click();await expect(page.locator('.history-publication')).toHaveCount(0);
});

test('removing the last filtered case keeps the modal operable and restores focus safely',async({page})=>{
 await openDemo(page);await openCampus(page);await addCase(page);await closeDialog(page);await page.getByRole('button',{name:/^优秀案例/}).click();
 await openCampus(page);await page.getByRole('button',{name:'移出优秀案例库',exact:true}).click();
 await expect(page.getByRole('button',{name:'加入优秀案例库',exact:true})).toBeEnabled();await closeDialog(page);
 await expect(page.getByRole('heading',{name:'还没有符合筛选的优秀案例',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'历史任务',exact:true})).toBeFocused();
 expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)!).ids,CASE_STORAGE_KEY)).toEqual([]);
});

test('reset is confirmed and only deletes this feature storage',async({page})=>{
 await openDemo(page);await openCampus(page);await addCase(page);await closeDialog(page);
 await page.evaluate(()=>{localStorage.setItem('hw-last-task','task-to-keep');localStorage.setItem('unrelated-preference','keep');});
 await page.getByRole('button',{name:'重置演示',exact:true}).click();await page.getByRole('button',{name:'取消',exact:true}).click();
 expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)!).ids.length,CASE_STORAGE_KEY)).toBe(1);
 await page.getByRole('button',{name:'重置演示',exact:true}).click();await page.getByRole('button',{name:'确认重置演示',exact:true}).click();
 expect(await page.evaluate(key=>localStorage.getItem(key),CASE_STORAGE_KEY)).toBeNull();
 expect(await page.evaluate(()=>[localStorage.getItem('hw-last-task'),localStorage.getItem('unrelated-preference')])).toEqual(['task-to-keep','keep']);
});

test('reference preview matches saved platform and scene, exposes no-match and opens original source',async({page})=>{
 const apiWrites:string[]=[];page.on('request',request=>{if(request.method()!=='GET')apiWrites.push(request.url());});
 await openDemo(page);await openCampus(page);await addCase(page);await page.getByRole('dialog').getByRole('button',{name:'预览下次参考',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'预览下次参考',exact:true})).toBeVisible();await expect(page.locator('.reference-match')).toHaveCount(1);
 await expect(page.getByRole('dialog')).toContainText('尚未被真实 Writer 加载');
 await page.getByLabel('演示发布平台',{exact:true}).selectOption('wechat');await expect(page.locator('.reference-match')).toHaveCount(0);await expect(page.getByRole('heading',{name:'这个平台和场景还没有收藏',exact:true})).toBeVisible();
 await page.getByLabel('演示发布平台',{exact:true}).selectOption('xiaohongshu');await page.getByLabel('演示营销场景',{exact:true}).selectOption('office');await expect(page.locator('.reference-match')).toHaveCount(0);
 await page.getByLabel('演示营销场景',{exact:true}).selectOption('campus');await page.getByRole('button',{name:'查看原示例与表现',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'推文与效果',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'已加入演示案例库',exact:true})).toBeVisible();
 expect(apiWrites).toEqual([]);
});

test('empty reference preview guides back to examples without pretending to learn',async({page})=>{
 await openDemo(page);await page.getByRole('button',{name:'预览下次参考',exact:true}).click();await expect(page.getByRole('heading',{name:'先留下一篇好案例',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'浏览演示任务',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.history-campaign')).toHaveCount(3);
});

test('unavailable storage reports current-page-only state instead of claiming persistence',async({page})=>{
 await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('blocked','SecurityError');};});
 await openDemo(page);await openCampus(page);await addCase(page);
 await expect(page.getByRole('dialog')).toContainText('本次操作仅在当前页面有效');await expect(page.locator('.history-case-status')).toHaveText('已加入当前页面，尚未确认持久保存');
 expect(await page.evaluate(key=>localStorage.getItem(key),CASE_STORAGE_KEY)).toBeNull();
});

test('corrupt local records have a recoverable empty state and unknown IDs cannot become cases',async({page})=>{
 await page.addInitScript(key=>localStorage.setItem(key,'{"version":1,"ids":"broken"}'),CASE_STORAGE_KEY);
 await openDemo(page);await expect(page.getByText('浏览器中的演示收藏无法读取，当前从空收藏开始；可用“重置演示”清理此功能的记录。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'重置演示',exact:true}).click();await page.getByRole('button',{name:'确认重置演示',exact:true}).click();
 await expect(page.getByText('浏览器中的演示收藏无法读取，当前从空收藏开始；可用“重置演示”清理此功能的记录。',{exact:true})).toHaveCount(0);
 await page.evaluate(key=>{localStorage.setItem(key,JSON.stringify({version:1,ids:['fixture-task','unknown-post',12]}));window.dispatchEvent(new StorageEvent('storage',{key}));},CASE_STORAGE_KEY);
 await expect(page.getByRole('button',{name:'优秀案例 0',exact:true})).toBeVisible();
});

for(const width of [1440,768,390])test(`effects, post detail and reference preview are usable at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:1050});await openDemo(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
 await page.screenshot({path:`qa/screenshots/history-effects-${width}.png`,fullPage:false});
 await openCampus(page);await addCase(page);
 expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
 await page.screenshot({path:`qa/screenshots/history-case-${width}.png`,fullPage:false});
 await page.getByRole('dialog').getByRole('button',{name:'预览下次参考',exact:true}).click();
 expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
 await page.screenshot({path:`qa/screenshots/history-reference-${width}.png`,fullPage:false});
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
});
