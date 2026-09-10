#!/usr/bin/env bash
set -euo pipefail
# Run on the existing server with a prepared staging directory as argument.
stage=${1:?staging directory required}
backend=/var/www/intermap-capture-server
site=/var/www/loop-lulu/intermap
nginx=/etc/nginx/conf.d/loop-lulu.conf
backup=/var/backups/intermap-1.0.18/$(date +%Y%m%d-%H%M%S)
mkdir -p "$backup"
cp "$backend/capture_server.js" "$backup/capture_server.js"
cp "$nginx" "$backup/nginx.conf"
node --check "$stage/capture_server.js"
node --check "$stage/training_evidence.js"
/opt/miniconda3/envs/ocr/bin/python -m py_compile "$stage/process_android_evidence.py"
cp -a "$site" "$stage/site"
cp "$stage/index.html" "$stage/site/index.html"
cp "$stage/training-review.html" "$stage/site/training-review.html"
find "$stage/site" -name '._*' -delete
cp "$stage/training_evidence.js" "$backend/training_evidence.js"
cp "$stage/process_android_evidence.py" "$backend/process_android_evidence.py"
cp "$stage/capture_server.js" "$backend/capture_server.js"
cp "$stage/nginx.conf" "$nginx"
if ! nginx -t; then
  cp "$backup/nginx.conf" "$nginx"
  cp "$backup/capture_server.js" "$backend/capture_server.js"
  exit 1
fi
mv "$site" "$backup/site"
mv "$stage/site" "$site"
chown -R nginx:nginx "$site"
cd "$backend"
if systemctl is-enabled --quiet intermap-capture.service 2>/dev/null; then
  systemctl restart intermap-capture.service
else
  pkill -f '^node capture_server.js$' || true
  nohup ./start.sh > /var/log/intermap-capture.log 2>&1 < /dev/null &
fi
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:3011/health > /dev/null; then healthy=1; break; fi
  sleep 1
done
if [ "$healthy" != 1 ]; then
  cp "$backup/capture_server.js" "$backend/capture_server.js"
  cp "$backup/nginx.conf" "$nginx"
  mv "$site" "$stage/failed-site"
  mv "$backup/site" "$site"
  nohup ./start.sh > /var/log/intermap-capture.log 2>&1 < /dev/null &
  exit 1
fi
nginx -s reload
printf 'Training v3 deployed. Rollback directory: %s\n' "$backup"
