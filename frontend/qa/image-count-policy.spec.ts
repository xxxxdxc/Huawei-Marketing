import {test,expect} from '@playwright/test';
import {POLICIES} from '../src/shared';
import {makeTask,mockApi} from './fixtures';
test('xiaohongshu image range is advice with a one-image floor',()=>{
 const p=POLICIES.xiaohongshu;
 expect(p.min).toBe(1);expect(p.max).toBe(Infinity);expect(p.recommended).toBe('3–6');
 expect(POLICIES.wechat.min).toBe(2);expect(POLICIES.wechat.max).toBe(4);
 expect(POLICIES.moments.min).toBe(1);expect(POLICIES.moments.max).toBe(3);
});
test('preview describes recommendation instead of a blocking range',async({page})=>{
 await mockApi(page,makeTask('approved','xiaohongshu'));await page.goto('/');
 await expect(page.locator('.platform-policy')).toContainText('推荐 3–6 张不同图片，至少 1 张');
});
