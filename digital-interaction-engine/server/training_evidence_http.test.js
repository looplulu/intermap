const test = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

test('HTTP training reads/writes require password and a valid upload seals correctly', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'training-http-'));
  const port = 31000 + Math.floor(Math.random() * 10000);
  const child = spawn(process.execPath, [path.join(__dirname, 'capture_server.js')], {
    env: {...process.env, PORT: String(port), TRAIN_PASSWORD: 'fixture-password', INTERMAP_DATA_DIR: root,
      INTERMAP_EVIDENCE_PROCESSOR: '/nonexistent-test-worker'}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  t.after(async () => { child.kill(); await new Promise(resolve => child.once('close', resolve)); fs.rmSync(root, {recursive: true, force: true}); });
  await new Promise((resolve, reject) => { child.stdout.once('data', resolve); child.once('error', reject); child.once('exit', code => reject(Error(`server exit ${code}`))); });
  const post = (route, body) => fetch(`http://127.0.0.1:${port}/api/${route}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  for (const operation of ['list', 'review', 'append', 'asset', 'finish', 'retry']) {
    assert.equal((await post('training-evidence', {operation})).status, 403);
  }
  assert.equal((await post('events', {session_id: 'test', event_type: 'session_start'})).status, 403);
  assert.equal((await post('rebuild-knowledge', {})).status, 403);
  const id = 'android_12345678-1234-1234-1234-123456789abc';
  const body = {password: 'fixture-password', operation: 'append', session_id: id,
    metadata: {schema_version: 3, session_id: id, package_name: 'test.app'},
    records: [{seq: 1, id: 'e_1', session_id: id, kind: 'session_start', payload: {}}]};
  const receipt = await (await post('training-evidence', body)).json();
  assert.equal(receipt.accepted_seq, 1);
  const finish = await (await post('training-evidence', {password: 'fixture-password', operation: 'finish', session_id: id, total_records: 1})).json();
  assert.equal(finish.complete, true);
  const list = await (await post('training-evidence', {password: 'fixture-password', operation: 'list'})).json();
  assert.equal(list.sessions.length, 1);
  assert.equal(JSON.stringify(list).includes('fixture-password'), false);
});
