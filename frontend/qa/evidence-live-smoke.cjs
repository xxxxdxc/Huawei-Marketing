// Read-only smoke: never confirms, refreshes evidence, or starts a model run.
const { chromium } = require('@playwright/test');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.FRONTEND_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
 const context=await browser.newContext({viewport:{width:1440,height:1050}});const page=await context.newPage();const errors=[],writes=[];
 await page.route('**/api/**',route=>{if(!['GET','HEAD'].includes(route.request().method())){writes.push(new URL(route.request().url()).pathname);return route.abort();}return route.continue();});
 page.on('pageerror',e=>errors.push(e.message));
 const response=await context.request.get('http://127.0.0.1:8765/api/tasks');const tasks=await response.json();
 let selected=null;
 for(const item of tasks){const r=await context.request.get('http://127.0.0.1:8765/api/tasks/'+item.id);const t=await r.json();if(t.brief_analysis&&t.package?.coverage&&!t.document&&!['planning','retrieving','analyzing'].includes(t.status)){selected=t;break;}}
 if(!selected){console.log(JSON.stringify({skipped:true,reason:'No stable pre-document task available; no writes performed'}));return;}
 await page.addInitScript(id=>localStorage.setItem('hw-last-task',id),selected.id);
 await page.goto('http://127.0.0.1:5174/');await page.getByRole('button',{name:'知识库依据',exact:true}).click();
 try { await page.getByRole('heading',{name:'尚未满足的需求'}).waitFor({timeout:10000}); } catch(e) { console.log(JSON.stringify({headings:await page.getByRole('heading').allTextContents(),alerts:await page.getByRole('alert').allTextContents(),errors,selectedStatus:selected.status,selectedVersion:selected.version})); await page.screenshot({path:'qa/screenshots/live-evidence-check.png',fullPage:true}); throw e; }
 const region=page.getByRole('region',{name:'资料检查结果与下一步'});
 const alerts=await region.getByRole('alert').allTextContents();
 await region.screenshot({path:'qa/screenshots/live-evidence-review-desktop.png'});
 await page.setViewportSize({width:390,height:844});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
 await region.screenshot({path:'qa/screenshots/live-evidence-review-mobile.png'});
 console.log(JSON.stringify({readOnly:true,version:selected.version,errors,writes,alerts,mobileOverflow:overflow}));
 if(errors.length||writes.length||alerts.length||overflow)process.exitCode=1;
 } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
