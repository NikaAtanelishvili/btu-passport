#!/bin/sh
# IN-05: used by the compose prod stack only (Railway gives secrets as variable contents and
# runs the image as `app` directly). Compose bind-mounts file secrets with the host's owner
# and mode, which the non-root `app` user can't read. Started as root, this copies each
# secret named by ISSUER_PRIVATE_KEY_FILE / GOOGLE_SHEETS_CREDENTIALS_FILE into /run/app
# (a tmpfs) as app:app 0400, points the variable at the copy, and runs the command as app.
set -eu
if [ "$(id -u)" = 0 ]; then
    for var in ISSUER_PRIVATE_KEY_FILE GOOGLE_SHEETS_CREDENTIALS_FILE; do
        eval "src=\${$var:-}"
        if [ -n "$src" ] && [ -f "$src" ]; then
            dst="/run/app/$(basename "$src")"
            install -m 0400 -o app -g app "$src" "$dst"
            export "$var=$dst"
        fi
    done
    exec setpriv --reuid=app --regid=app --init-groups -- "$@"
fi
exec "$@"
