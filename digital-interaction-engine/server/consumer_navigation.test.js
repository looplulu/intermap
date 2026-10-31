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
test('unauthorized frame requests cannot invoke the model',async()=>{
  const store=new ConsumerNavigation('/unused',()=>{throw Error('must not run');});
  await assert.rejects(store.dispatch('frame',{},'bad','test'),/UNAUTHORIZED/);
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
