#!/usr/bin/env python3
"""Run on the deployment host. Only creates/removes its own synthetic session."""
import base64
import hashlib
import io
import json
from pathlib import Path
import os
import shutil
import time
import urllib.request
import uuid
from PIL import Image, ImageDraw, ImageFont

password = os.environ['INTERMAP_TRAIN_PASSWORD']
endpoint = 'https://loop-lulu.com/intermap/api/training-evidence'
session = 'android_' + str(uuid.uuid4())
directory = Path('/var/www/intermap-data/android_training_v3') / session


def post(operation, **values):
    body = dict(operation=operation, password=password, session_id=session, **values)
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)
    assert data.get('ok'), data
    return data


def screenshot(label):
    image = Image.new('RGB', (360, 720), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=20)
    draw.text((20, 20), 'SYNTHETIC TEST', fill='black', font=font)
    draw.rectangle((220, 70, 350, 160), fill='#397b44')
    draw.text((228, 105), label, fill='white', font=font)
    buf = io.BytesIO(); image.save(buf, format='JPEG', quality=90)
    return buf.getvalue()


def record(seq, kind, timestamp, payload):
    return dict(id=f'e_{seq}', seq=seq, session_id=session, kind=kind, uptime_ms=timestamp, payload=payload)


def main():
    images = [screenshot('Orders'), screenshot('Order list')]
    assets = {f'f_{i+1}.jpg': base64.b64encode(image).decode() for i, image in enumerate(images)}
    frames = [dict(uptime_ms=t, asset=f'f_{i+1}.jpg', sha256=hashlib.sha256(image).hexdigest(),
                   screen_width=360, screen_height=720, image_width=360, image_height=720, rotation=0)
              for i, (image, t) in enumerate(zip(images, [100, 700]))]
    records = [record(1, 'session_start', 0, {}), record(2, 'frame', 100, frames[0]),
               record(3, 'accessibility', 250, dict(event_type=1, event_uptime_ms=250,
                      position_source='accessibility_node_bounds', touch_point=None,
                      source=dict(text='Orders', bounds=dict(left=220, top=70, right=350, bottom=160)))),
               record(4, 'frame', 700, frames[1]), record(5, 'session_end', 900, {})]
    metadata = dict(schema_version=3, session_id=session, package_name='test.intermap.synthetic',
                    app='合成验证', app_label='合成验证', started_at_ms=int(time.time()*1000), is_test=True)
    assert post('append', metadata=metadata, records=records, assets=assets)['accepted_seq'] == 5
    assert post('append', metadata=metadata, records=records, assets=assets)['accepted_seq'] == 5
    assert post('asset', asset='f_1.jpg')['image'].endswith(assets['f_1.jpg'])
    assert post('finish', total_records=5)['complete']
    print('HTTPS upload, duplicate retry, image readback and complete receipt passed.', flush=True)
    deadline = time.time()+260
    while time.time() < deadline:
        result = post('review')
        state = result.get('processing') or {}
        if state.get('status') == 'ready_for_review':
            step = result['review']['interactions'][0]
            assert step['gui_evidence']['target']['ok']
            assert step['gui_evidence']['before']['ok']
            assert step['gui_evidence']['after']['ok']
            assert step['touch_point'] is None
            print('Cloud GUI/OCR before/target/after enrichment passed; candidate remains pending_review.', flush=True)
            shutil.rmtree(directory)
            print('Synthetic session removed; real training data untouched.', flush=True)
            return
        if state.get('status') in ('failed', 'retry_pending'):
            raise RuntimeError('Background processing failed: '+json.dumps(state, ensure_ascii=False))
        time.sleep(3)
    raise RuntimeError('Background processing did not finish in 260 seconds; test session retained for diagnosis: '+session)


if __name__ == '__main__': main()
