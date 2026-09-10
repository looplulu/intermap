#!/usr/bin/env python3
"""Build evidence-linked candidates, then enrich them asynchronously with GUI/OCR.

No output here is published into Golden Flow. Raw native bounds are never
represented as an observed touch point, and a model suggestion is not an action.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.request


def read(file):
    return json.loads(file.read_text())


def write(file, value):
    tmp = file.with_suffix(file.suffix + '.tmp')
    with tmp.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(file)


def build_review(records, metadata):
    frames = sorted((r for r in records if r['kind'] == 'frame'), key=lambda r: r['payload']['uptime_ms'])
    actions = [r for r in records if r['kind'] == 'accessibility' and r['payload'].get('event_type') in (1, 2, 4096, 16)]
    actions.sort(key=lambda r: (r['payload']['event_uptime_ms'], r['seq']))
    gaps = [r for r in records if r['kind'] in ('capture_gap', 'pause')]
    interactions, nodes, edges = [], {}, []
    for index, action in enumerate(actions):
        p = action['payload']
        timestamp = p['event_uptime_ms']
        next_time = actions[index + 1]['payload']['event_uptime_ms'] if index + 1 < len(actions) else timestamp + 2500
        before = [f for f in frames if 0 <= timestamp - f['payload']['uptime_ms'] <= 1000]
        after = [f for f in frames if timestamp + 150 <= f['payload']['uptime_ms'] < min(next_time, timestamp + 2500)]
        before = before[-1] if before else None
        # Prefer a later frame for animations, but never cross another action.
        after = after[-1] if after else None
        source = p.get('source') or {}
        bounds = source.get('bounds')
        issues = []
        if not before: issues.append('missing_before_frame')
        if not after: issues.append('missing_after_frame_or_rapid_actions')
        if not bounds: issues.append('missing_source_bounds')
        if source.get('editable'): issues.append('editable_target_redacted')
        if p.get('tree_truncated'): issues.append('tree_truncated')
        if before and index > 0 and before['payload']['uptime_ms'] <= actions[index - 1]['payload']['event_uptime_ms']:
            issues.append('before_frame_predates_previous_action')
        if before and after:
            a, b = before['payload'], after['payload']
            if (a['screen_width'], a['screen_height'], a['rotation']) != (b['screen_width'], b['screen_height'], b['rotation']):
                issues.append('display_geometry_changed')
            if any(a['uptime_ms'] <= g['uptime_ms'] <= b['uptime_ms'] for g in gaps):
                issues.append('capture_gap_between_frames')
        normalized = None
        if bounds and before:
            f = before['payload']
            l, t, r, b = (bounds[k] for k in ('left', 'top', 'right', 'bottom'))
            if 0 <= l < r <= f['screen_width'] and 0 <= t < b <= f['screen_height']:
                normalized = dict(x=l / f['screen_width'], y=t / f['screen_height'],
                                  w=(r - l) / f['screen_width'], h=(b - t) / f['screen_height'])
                if normalized['w'] * normalized['h'] > .4: issues.append('broad_source_bounds')
            else: issues.append('bounds_outside_frame')
        item = dict(action_id=action['id'], action_type={1: 'click', 2: 'long_press', 4096: 'scroll', 16: 'text_change'}[p['event_type']],
                    event_uptime_ms=timestamp, source=source, position_source=p.get('position_source'),
                    touch_point=p.get('touch_point'), target_bounds_norm=normalized,
                    before=before, after=after, issues=issues, review_status='pending_review',
                    annotations=[r['payload'] for r in records if r['kind'] == 'annotation' and r['payload'].get('action_id') == action['id']])
        interactions.append(item)
        for frame in (before, after):
            if frame:
                node_id = frame['payload']['sha256']
                nodes[node_id] = dict(node_id=node_id, frame_id=frame['id'], asset=frame['payload']['asset'],
                                      identity='exact_visual_observation_not_semantic_page')
        if before and after and not issues:
            edges.append(dict(from_node=before['payload']['sha256'], to_node=after['payload']['sha256'],
                              action_id=action['id'], outcome='same_pixels' if before['payload']['sha256'] == after['payload']['sha256'] else 'visual_change',
                              review_status='pending_review'))
    return dict(schema_version=3, metadata=metadata, review_status='pending_review',
                interactions=interactions, nodes=list(nodes.values()), edges=edges,
                capture_gaps=gaps, frame_count=len(frames), record_count=len(records))


def infer(image, task, metadata, endpoint):
    request = dict(image='data:image/jpeg;base64,' + base64.b64encode(image).decode(),
                   app=metadata['package_name'], task=task, fast_navigation=False, include_ocr_evidence=True)
    req = urllib.request.Request(endpoint, data=json.dumps(request).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=65) as response:
        result = json.load(response)
    if not result.get('ok'): raise RuntimeError(str(result.get('error', 'GUI failed')))
    return result


def process_session(directory, endpoint, analyze=True, budget=20):
    receipt = read(directory / 'receipt.json')
    if not receipt.get('complete'): return
    state_file = directory / 'processing.json'
    if state_file.exists():
        state = read(state_file)
        if state.get('status') == 'ready_for_review' or state.get('retry_at', 0) > time.time(): return
    meta = read(directory / 'metadata.json')
    records = [read(directory / 'records' / f'{i}.json') for i in range(1, receipt['accepted_seq'] + 1)]
    review = build_review(records, meta)
    review['interrupted'] = receipt.get('interrupted', False)
    write(directory / 'review.json', review)
    write(state_file, dict(status='analyzing', interactions=len(review['interactions']), completed=0))
    results_dir = directory / 'analysis'
    results_dir.mkdir(exist_ok=True)
    calls = 0
    errors = []
    for item in review['interactions']:
        if not item['before'] or not item['target_bounds_norm'] or item['source'].get('editable'): continue
        file = results_dir / f"{item['action_id']}.json"
        if file.exists():
            item['gui_evidence'] = read(file)
            continue
        if not analyze or calls >= budget: continue
        try:
            from PIL import Image
            f = item['before']['payload']
            image = (directory / 'frames' / f['asset']).read_bytes()
            rect = item['target_bounds_norm']
            source = Image.open(io.BytesIO(image))
            w, h = source.size
            crop = source.crop((int(rect['x']*w), int(rect['y']*h), max(int((rect['x']+rect['w'])*w), int(rect['x']*w)+1), max(int((rect['y']+rect['h'])*h), int(rect['y']*h)+1)))
            out = io.BytesIO(); crop.save(out, format='JPEG', quality=92)
            # The crop is from BEFORE the action. The prompt never asks the model to guess a previous click.
            target = infer(out.getvalue(), '这是一张用户实际操作目标区域的裁剪图。仅描述实际可见的文字和图标外观，不推测下一步，不推荐退款售后等路径。无文字时明确说无文字。', meta, endpoint)
            context = infer(image, '仅识别当前页面名称、可见布局与状态，不推荐操作。训练目标由无障碍位置另行确定。', meta, endpoint)
            after_result = None
            if item['after']:
                after_image = (directory / 'frames' / item['after']['payload']['asset']).read_bytes()
                after_result = infer(after_image, '仅识别当前页面名称、可见布局与状态，不推荐操作。不要假定任务已成功。', meta, endpoint)
            evidence = dict(source='gui_inference', review_status='pending_review', target=target, before=context, after=after_result,
                            target_crop_bounds=rect, before_frame_id=item['before']['id'])
            write(file, evidence)
            item['gui_evidence'] = evidence
        except Exception as error:
            errors.append(dict(action_id=item['action_id'], error=str(error)))
        calls += 1
        write(directory / 'review.json', review)
        write(state_file, dict(status='analyzing', completed=sum('gui_evidence' in x for x in review['interactions']), interactions=len(review['interactions'])))
    remaining = sum(bool(x['before'] and x['target_bounds_norm'] and not x['source'].get('editable') and 'gui_evidence' not in x) for x in review['interactions'])
    write(directory / 'review.json', review)
    write(state_file, dict(status='retry_pending' if errors else 'queued' if remaining else 'ready_for_review',
                          remaining=remaining, completed=sum('gui_evidence' in x for x in review['interactions']),
                          errors=errors, retry_at=time.time()+120 if errors else 0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/var/www/intermap-data/android_training_v3')
    parser.add_argument('--endpoint', default='http://127.0.0.1:3011/api/ui-tars')
    parser.add_argument('--no-gui', action='store_true')
    args = parser.parse_args()
    for directory in sorted(Path(args.root).glob('android_*')):
        try: process_session(directory, args.endpoint, not args.no_gui)
        except Exception as error:
            write(directory / 'processing.json', dict(status='failed', error=str(error), retry_at=time.time()+120))
    aggregate(Path(args.root))


def aggregate(root):
    groups = {}
    for file in root.glob('android_*/review.json'):
        review = read(file)
        meta = review['metadata']
        if meta.get('is_test'): continue
        identity = [meta.get(k) for k in ('package_name', 'target_version', 'android_version', 'model', 'font_scale')]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
        group = groups.setdefault(key, dict(environment=identity, source='android_a11y_gui_v3',
            review_status='pending_review', sessions=[], nodes={}, edges=[]))
        session = meta['session_id']
        group['sessions'].append(session)
        for node in review['nodes']:
            stored = group['nodes'].setdefault(node['node_id'], dict(node_id=node['node_id'], evidence=[]))
            stored['evidence'].append(dict(session_id=session, frame_id=node['frame_id'], asset=node['asset']))
        group['edges'].extend(dict(edge, session_id=session) for edge in review['edges'])
    output = root / 'maps'
    output.mkdir(parents=True, exist_ok=True)
    for key, group in groups.items():
        group['nodes'] = list(group['nodes'].values())
        write(output / f'{key}.json', group)


if __name__ == '__main__': main()
