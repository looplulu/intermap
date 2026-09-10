const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const {TrainingEvidenceStore} = require('./training_evidence');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'evidence-test-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const store = new TrainingEvidenceStore(root);
  const id = 'android_12345678-1234-1234-1234-123456789abc';
  const meta = {schema_version: 3, session_id: id, package_name: 'test.app'};
  const record = (seq, kind = 'accessibility', payload = {}) => ({seq, id: `e_${seq}`, session_id: id, kind, payload});
  const request = records => ({operation: 'append', session_id: id, metadata: meta, records});
  return {store, id, meta, record, request};
}
test('retries are idempotent; mutation and sequence gaps are rejected', t => {
  const {store, id, record, request} = fixture(t);
  const batch = request([record(1), record(2)]);
  assert.equal(store.handle(batch).accepted_seq, 2);
  assert.equal(store.handle(batch).accepted_seq, 2);
  assert.throws(() => store.handle(request([record(4)])), /missing preceding/);
  assert.throws(() => store.handle(request([record(2, 'frame', {})])), /invalid frame/);
  assert.throws(() => store.handle(request([record(1, 'accessibility', {text: 'changed'})])), /immutable/);
  assert.throws(() => store.handle({operation: 'finish', session_id: id, total_records: 3}), /count mismatch/);
  assert.equal(store.handle({operation: 'finish', session_id: id, total_records: 2}).complete, true);
  assert.throws(() => store.handle(request([record(3)])), /sealed/);
  assert.equal(store.handle(batch).accepted_seq, 2);
});
test('images must be present and match the checksum before acknowledgement', t => {
  const {store, record, request} = fixture(t);
  const bytes = Buffer.from([255, 216, 1, 2, 255, 217]);
  const hash = crypto.createHash('sha256').update(bytes).digest('hex');
  const batch = request([record(1, 'frame', {asset: 'f_1.jpg', sha256: hash})]);
  assert.throws(() => store.handle(batch), /missing image/);
  batch.assets = {'f_1.jpg': Buffer.from('wrong').toString('base64')};
  assert.throws(() => store.handle(batch), /checksum/);
  batch.assets['f_1.jpg'] = bytes.toString('base64');
  assert.equal(store.handle(batch).accepted_seq, 1);
  delete batch.assets;
  assert.equal(store.handle(batch).accepted_seq, 1);
});
test('session and asset path traversal are rejected', t => {
  const {store, id, record, request} = fixture(t);
  assert.throws(() => store.handle({operation: 'append', session_id: '../secret'}), /invalid session/);
  store.handle(request([record(1)]));
  assert.throws(() => store.handle({operation: 'asset', session_id: id, asset: '../metadata.json'}), /invalid asset/);
});
test('a retried batch repairs records committed before a missing receipt', t => {
  const {store, id, record, request} = fixture(t);
  const batch = request([record(1), record(2)]);
  store.handle(batch);
  fs.unlinkSync(path.join(store.session(id), 'receipt.json'));
  assert.equal(store.handle(batch).accepted_seq, 2);
});
