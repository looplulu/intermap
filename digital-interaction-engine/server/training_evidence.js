const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const digest = value => crypto.createHash('sha256').update(value).digest('hex');
function atomic(file, value) {
  const tmp = `${file}.tmp`;
  const fd = fs.openSync(tmp, 'w', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  fs.renameSync(tmp, file);
}
function read(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function requireValue(condition, message) { if (!condition) throw new Error(message); }

class TrainingEvidenceStore {
  constructor(root) { this.root = path.join(root, 'android_training_v3'); }
  session(id) {
    requireValue(/^android_[a-f0-9-]{36}$/.test(id || ''), 'invalid session id');
    return path.join(this.root, id);
  }
  handle(data) {
    if (data.operation === 'list') {
      if (!fs.existsSync(this.root)) return {ok: true, sessions: []};
      const sessions = fs.readdirSync(this.root).filter(id => /^android_[a-f0-9-]{36}$/.test(id))
        .filter(id => fs.existsSync(path.join(this.session(id), 'metadata.json')) && fs.existsSync(path.join(this.session(id), 'receipt.json')))
        .map(id => {
          const dir = this.session(id);
          return {metadata: read(path.join(dir, 'metadata.json')), receipt: read(path.join(dir, 'receipt.json')),
            processing: fs.existsSync(path.join(dir, 'processing.json')) ? read(path.join(dir, 'processing.json')) : null};
        }).sort((a, b) => b.metadata.started_at_ms - a.metadata.started_at_ms);
      return {ok: true, sessions};
    }
    const dir = this.session(data.session_id);
    const receiptFile = path.join(dir, 'receipt.json');
    if (data.operation === 'append') return this.append(dir, data);
    requireValue(fs.existsSync(receiptFile), 'session not found');
    const receipt = read(receiptFile);
    if (data.operation === 'finish') {
      requireValue(Number.isInteger(data.total_records) && data.total_records === receipt.accepted_seq, 'record count mismatch');
      receipt.complete = true;
      receipt.interrupted = data.interrupted === true;
      receipt.truncated_tail_bytes = Number(data.truncated_tail_bytes || 0);
      receipt.review_status = 'pending_review';
      atomic(receiptFile, receipt);
      return {ok: true, ...receipt};
    }
    if (data.operation === 'review') {
      return {ok: true, receipt, metadata: read(path.join(dir, 'metadata.json')),
        review: fs.existsSync(path.join(dir, 'review.json')) ? read(path.join(dir, 'review.json')) : null,
        processing: fs.existsSync(path.join(dir, 'processing.json')) ? read(path.join(dir, 'processing.json')) : null};
    }
    if (data.operation === 'asset') {
      requireValue(/^f_\d+\.jpg$/.test(data.asset || ''), 'invalid asset');
      const file = path.join(dir, 'frames', data.asset);
      requireValue(fs.existsSync(file), 'asset not found');
      return {ok: true, image: `data:image/jpeg;base64,${fs.readFileSync(file).toString('base64')}`};
    }
    if (data.operation === 'retry') {
      const file = path.join(dir, 'processing.json');
      if (fs.existsSync(file)) fs.unlinkSync(file);
      return {ok: true, queued: true};
    }
    throw new Error('unknown operation');
  }
  append(dir, data) {
    if (fs.existsSync(this.root) && fs.statfsSync) {
      const disk = fs.statfsSync(this.root);
      requireValue(disk.bavail * disk.bsize > 512 * 1024 * 1024, 'server storage low; retain local evidence');
    }
    const records = data.records;
    requireValue(Array.isArray(records) && records.length > 0 && records.length <= 32, 'invalid batch size');
    requireValue(data.metadata?.schema_version === 3 && data.metadata.session_id === data.session_id, 'invalid metadata');
    requireValue(typeof data.metadata.package_name === 'string' && data.metadata.package_name.length < 200, 'invalid package');
    const assets = data.assets || {};
    const prepared = [];
    for (let i = 0; i < records.length; i++) {
      const r = records[i];
      requireValue(Number.isInteger(r.seq) && r.seq > 0 && r.id === `e_${r.seq}` && r.session_id === data.session_id, 'invalid event identity');
      requireValue(i === 0 || r.seq === records[i - 1].seq + 1, 'non-contiguous batch');
      requireValue(r.payload && typeof r.payload === 'object', 'missing payload');
      requireValue(JSON.stringify(r).length < 1500000, 'event too large');
      if (r.kind === 'frame') {
        const p = r.payload;
        requireValue(/^f_\d+\.jpg$/.test(p.asset || '') && /^[a-f0-9]{64}$/.test(p.sha256 || ''), 'invalid frame');
        const existing = path.join(dir, 'frames', p.asset);
        let bytes;
        if (Object.hasOwn(assets, p.asset)) {
          requireValue(typeof assets[p.asset] === 'string' && assets[p.asset].length <= 7000000, 'invalid image size');
          bytes = Buffer.from(assets[p.asset], 'base64');
        } else {
          requireValue(fs.existsSync(existing), 'missing image');
          bytes = fs.readFileSync(existing);
        }
        requireValue(bytes.length > 4 && bytes[0] === 255 && bytes[1] === 216 && digest(bytes) === p.sha256, 'image checksum mismatch');
        if (fs.existsSync(existing)) requireValue(digest(fs.readFileSync(existing)) === p.sha256, 'immutable image conflict');
        prepared.push({name: p.asset, bytes});
      }
    }
    fs.mkdirSync(path.join(dir, 'records'), {recursive: true, mode: 0o700});
    fs.mkdirSync(path.join(dir, 'frames'), {recursive: true, mode: 0o700});
    const metaFile = path.join(dir, 'metadata.json');
    if (fs.existsSync(metaFile)) requireValue(JSON.stringify(read(metaFile)) === JSON.stringify(data.metadata), 'immutable metadata conflict');
    else atomic(metaFile, data.metadata);
    const receiptFile = path.join(dir, 'receipt.json');
    let receipt = fs.existsSync(receiptFile) ? read(receiptFile) : {session_id: data.session_id, accepted_seq: 0, complete: false};
    requireValue(records[0].seq <= receipt.accepted_seq + 1, 'missing preceding records');
    if (receipt.complete) requireValue(records.at(-1).seq <= receipt.accepted_seq, 'session already sealed');
    // Validate the entire batch before committing any evidence.
    for (const r of records) {
      const file = path.join(dir, 'records', `${r.seq}.json`);
      if (fs.existsSync(file)) requireValue(JSON.stringify(read(file)) === JSON.stringify(r), 'immutable event conflict');
      else requireValue(r.seq > receipt.accepted_seq, 'missing committed event');
    }
    for (const asset of prepared) {
      const file = path.join(dir, 'frames', asset.name);
      if (!fs.existsSync(file)) {
        const fd = fs.openSync(`${file}.tmp`, 'w', 0o600);
        try { fs.writeFileSync(fd, asset.bytes); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
        fs.renameSync(`${file}.tmp`, file);
      }
    }
    for (const r of records) {
      const file = path.join(dir, 'records', `${r.seq}.json`);
      if (!fs.existsSync(file)) atomic(file, r);
    }
    receipt.accepted_seq = Math.max(receipt.accepted_seq, records.at(-1).seq);
    receipt.updated_at = new Date().toISOString();
    atomic(receiptFile, receipt);
    return {ok: true, accepted_seq: records.at(-1).seq, complete: receipt.complete};
  }
}
module.exports = {TrainingEvidenceStore};
