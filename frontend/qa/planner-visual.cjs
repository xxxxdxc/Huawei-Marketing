const { chromium } = require('@playwright/test');
(async () => {
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1050}});
 await page.goto('http://127.0.0.1:5174/?preview=planner-v2');
 await page.locator('.planner-analysis').screenshot({path:'qa/screenshots/planner-selection-desktop.png'});
 await page.locator('.planner-selection-actions').screenshot({path:'qa/screenshots/planner-selection-actions-desktop.png'});
 await page.locator('.planner-composition summary').click();
 await page.locator('.planner-composition').screenshot({path:'qa/screenshots/planner-composition-desktop.png'});
 await page.locator('.plan-card').first().screenshot({path:'qa/screenshots/planner-v2-section-desktop.png'});
 await page.setViewportSize({width:390,height:1050});
 await page.locator('.planner-analysis').screenshot({path:'qa/screenshots/planner-selection-mobile.png'});
 await page.locator('.plan-card').first().screenshot({path:'qa/screenshots/planner-v2-section-mobile.png'});
 await browser.close();
})();
