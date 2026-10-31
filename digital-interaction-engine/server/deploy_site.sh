#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
site="$root/digital-interaction-demo"
version=$(cat "$site/VERSION")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
node --check "$site/assets/website.js"

stage=$(ssh root@loop-lulu.com 'mktemp -d /var/www/loop-lulu/.intermap-stage.XXXXXX')
[[ "$stage" == /var/www/loop-lulu/.intermap-stage.* ]]
COPYFILE_DISABLE=1 tar -C "$site" -cf - \
  index.html workbench.html training-review.html VERSION \
  assets/website.css assets/website.js assets/logo-web.png assets/logo.png \
  assets/demo-data.js assets/hero-illustration.png | \
  ssh root@loop-lulu.com "tar -C '$stage' -xf -"

ssh root@loop-lulu.com bash -s -- "$stage" "$version" <<'REMOTE'
set -euo pipefail
stage=$1
version=$2
site=/var/www/loop-lulu/intermap
backup=/var/backups/intermap-site
mkdir -p "$backup"
backup=$(mktemp -d "$backup/$version.XXXXXX")
test -s "$stage/index.html"
test -s "$stage/workbench.html"
test -s "$stage/training-review.html"
node --check "$stage/assets/website.js"
chown -R nginx:nginx "$stage"
chmod -R a+rX "$stage"
mv "$site" "$backup/site"
if ! mv "$stage" "$site"; then
  mv "$backup/site" "$site"
  exit 1
fi
if ! curl -fsS --resolve loop-lulu.com:443:127.0.0.1 \
    https://loop-lulu.com/intermap/ | grep 'assets/website.js' > /dev/null; then
  mv "$site" "$backup/failed-site"
  mv "$backup/site" "$site"
  echo 'Homepage verification failed; previous site restored.' >&2
  exit 1
fi
printf 'Deployed website %s. Previous site: %s/site\n' "$version" "$backup"
REMOTE
