#!/bin/sh
set -eu
# This volume belongs exclusively to this container. Recreated containers can
# inherit Chromium's process lock from the previous container hostname.
rm -f /profile/SingletonLock /profile/SingletonSocket /profile/SingletonCookie
exec chromium --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --password-store=basic --user-data-dir=/profile \
  --remote-debugging-port=9222 '--remote-allow-origins=*' \
  --window-size=1440,900 --start-maximized about:blank
