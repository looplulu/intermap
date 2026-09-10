const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true,channel:'chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const html=fs.readFileSync(path.join(__dirname,'../../digital-interaction-demo/training-review.html'),'utf8');
    const image=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=720;c.height=1600;const x=c.getContext('2d');x.fillStyle='#ffffff';x.fillRect(0,0,720,1600);x.fillStyle='#edf4ee';x.fillRect(0,0,720,240);x.fillStyle='#286a37';x.font='32px sans-serif';x.fillText('采集测试页面',36,58);x.fillRect(540,80,180,160);x.fillStyle='#ffffff';x.font='24px sans-serif';x.fillText('我的订单',574,160);x.fillStyle='#333333';x.font='28px sans-serif';x.fillText('用于验证画面和目标范围对齐',36,340);return c.toDataURL('image/png')});
    const metadata={app:'抖音',app_label:'抖音',session_id:'android_fixture',started_at_ms:1789000000000,manufacturer:'vivo',model:'Y300 Pro（测试夹具）',android_version:'15',target_version:'40.3'};
    const frame={id:'e_1',payload:{asset:'f_1.jpg',image_width:720,image_height:1600}};
    await page.route('https://review-test.local/**',async route=>{
      if(!route.request().url().includes('/api/')){await route.fulfill({contentType:'text/html',body:html});return}
      const data=route.request().postDataJSON();
      if(data.password!=='fixture'){await route.fulfill({status:403,json:{ok:false,error:'invalid training password'}});return}
      const responses={list:{ok:true,sessions:[{metadata,receipt:{accepted_seq:40,complete:true}}]},review:{ok:true,metadata,processing:{status:'ready_for_review'},review:{interactions:[{action_id:'e_2',action_type:'click',source:{text:'我的订单',bounds:{left:810,top:120,right:1080,bottom:360}},position_source:'accessibility_node_bounds',touch_point:null,before:frame,after:frame,target_bounds_norm:{x:.75,y:.05,w:.25,h:.1},issues:[],annotations:[]}]}},asset:{ok:true,image},retry:{ok:true,queued:true}};
      await route.fulfill({json:responses[data.operation]});
    });
    await page.goto('https://review-test.local/training-review.html');
    await page.locator('#password').fill('wrong');await page.getByRole('button',{name:'验证并读取'}).click();
    await page.getByText('invalid training password',{exact:true}).waitFor();
    await page.locator('#password').fill('fixture');await page.getByRole('button',{name:'验证并读取'}).click();
    await page.locator('.session').click();await page.locator('#after img').waitFor();
    assert.equal(await page.locator('#before .bounds').count(),1);
    assert.ok((await page.locator('#evidence').textContent()).includes('"touch_point": null'));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/private/tmp/intermap-training-review.png',fullPage:true});
    console.log('Review UI: auth, selection, frames, bounds overlay and desktop layout passed.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
