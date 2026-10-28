"""Container healthcheck (IN-05), stdlib only. The worker has no HTTP port: it is healthy
while its loop keeps touching WORKER_HEARTBEAT_FILE. Every other container is healthy when
HEALTHCHECK_PATH (default: the API's /api/healthz) answers 200 on $HOST:$PORT."""

import os
import sys
import time
import urllib.request

heartbeat = os.environ.get("WORKER_HEARTBEAT_FILE", "")
if heartbeat:
    try:
        sys.exit(0 if time.time() - os.path.getmtime(heartbeat) < 300 else 1)
    except OSError:
        sys.exit(1)

# HOST=:: (Railway) listens on IPv6 only.
local = "[::1]" if ":" in os.environ.get("HOST", "") else "127.0.0.1"
port = os.environ.get("PORT", "8000")
url = f"http://{local}:{port}{os.environ.get('HEALTHCHECK_PATH', '/api/healthz')}"
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        sys.exit(0 if response.status == 200 else 1)
except OSError:
    sys.exit(1)
