const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {ConsumerNavigation, normalize} = require('./consumer_navigation');

test('private screen strings and images never enter opt-in journals', async () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'consumer-test-'));
  try {
    const store=new ConsumerNavigation(root,async()=>({page_type:'orders',action:'choose',step_text:'选择私人订单123456',target_key:'右上方我的订单购物车123456',expected_result:'订单详情',model:'test'}));
    const s=store.create({goal:'私人目标123456',consent:true},'test');
    await store.dispatch('frame',{image:'data:image/jpeg;base64,/9j/AA=='},s.token,'test');
    const text=fs.readFileSync(path.join(root,'consumer_feedback_v1',s.session_id+'.jsonl'),'utf8');
    assert(!text.includes('123456')); assert(!text.includes('/9j/')); assert(text.includes('gui_inference'));
    assert(text.includes('我的订单')); assert(text.includes('top_right')); assert(text.includes('cart'));
    await store.dispatch('feedback',{feedback:'completed'},s.token,'test');
    const final=fs.readFileSync(path.join(root,'consumer_feedback_v1',s.session_id+'.jsonl'),'utf8');
    assert(final.includes('user_report_only')); assert(final.includes('pending_review'));
    await assert.rejects(store.dispatch('feedback',{feedback:'completed'},s.token,'test'),/UNAUTHORIZED/);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('no opt-in produces no persistent feedback files', async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'consumer-test-'));
  try { const store=new ConsumerNavigation(root); store.create({goal:'查订单'},'test'); assert.deepEqual(fs.readdirSync(root),[]); }
  finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('unknown outcomes and invented action types are rejected',()=>{
  assert.throws(()=>normalize({page_type:'orders',action:'auto_click',step_text:'点击'}),/INVALID_MODEL/);
});
test('any app identity and stable page keys survive normalization',()=>{
  const result=normalize({app_key:'com.example.camera',page_type:'other',page_key:'camera/settings',action:'click',step_text:'点击左上角设置'});
  assert.equal(result.app_key,'com.example.camera'); assert.equal(result.page_key,'camera/settings');
});
test('WeChat aliases cannot manufacture a page change',()=>{
  const base={page_type:'profile',action:'click',step_text:'点击头像'};
  const a=normalize({...base,app_key:'weixin',page_key:'weixin/profile'});
  const b=normalize({...base,app_key:'com.tencent.mm',page_key:'com.tencent.mm/profile'});
  assert.equal(a.page_key,b.page_key); assert.equal(a.app_key,b.app_key);
});
test('unauthorized frame requests cannot invoke the model',async()=>{
  const store=new ConsumerNavigation('/unused',()=>{throw Error('must not run');});
  await assert.rejects(store.dispatch('frame',{},'bad','test'),/UNAUTHORIZED/);
});
test('DeepSeek can be selected for normal visual navigation without replan',async(t)=>{
  const keys=['CONSUMER_VISION_PROVIDER','DEEPSEEK_API_KEY'];
  const saved=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  const fetchBefore=global.fetch;
  t.after(()=>{ global.fetch=fetchBefore; for(const k of keys) { if(saved[k]===undefined) delete process.env[k]; else process.env[k]=saved[k]; } });
  process.env.CONSUMER_VISION_PROVIDER='deepseek'; process.env.DEEPSEEK_API_KEY='test-only';
  global.fetch=async(url,options)=>{
    assert.equal(url,'https://api.deepseek.com/chat/completions');
    const body=JSON.parse(options.body);
    assert.equal(body.model,'deepseek-flash'); assert.equal(body.thinking.type,'disabled');
    assert.equal(body.response_format.type,'json_object');
    assert(body.messages[0].content[0].text.includes('开启=不共享'));
    return {ok:true,json:async()=>({choices:[{message:{content:JSON.stringify({page_type:'settings',action:'click',step_text:'点击底部开始'})}}]})};
  };
  const result=await new ConsumerNavigation('/unused').callModel({goal:'导航',history:[],image:'data:image/jpeg;base64,/9j/AA==',replan:false});
  assert.equal(result.model,'deepseek-flash');
});
test('feedback survives a server restart, is idempotent and only creates pending groups',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'consumer-restart-'));
  try {
    const model=async()=>({app_key:'douyin',page_type:'orders',action:'choose',target_role:'item_choice',step_text:'选择订单'});
    const first=new ConsumerNavigation(root,model);
    const session=first.create({goal:'查订单',consent:true,environment:{platform:'android',device_model:'V2410',width:1080,private_field:'secret'}},'test');
    await first.dispatch('frame',{image:'data:image/jpeg;base64,/9j/AA=='},session.token,'test');
    const restarted=new ConsumerNavigation(root,model);
    const event={feedback:'completed',event_id:'same-event',step_id:1};
    await restarted.dispatch('feedback',event,session.token,'test');
    await restarted.dispatch('feedback',event,session.token,'test');
    const review=restarted.review();
    assert.equal(review.sessions[0].feedback.length,1);
    assert.equal(review.groups[0].ready_for_navigation,false);
    assert.equal(review.groups[0].task_type,'find_order');
    assert.deepEqual(review.groups[0].nodes,['douyin:orders']);
    assert(!JSON.stringify(review).includes('private_field'));
    await assert.rejects(restarted.dispatch('frame',{},session.token,'test'),/UNAUTHORIZED/);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
