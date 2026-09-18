#!/bin/sh
set -e

if [ -z "$BM_KEY" ]; then
    echo "[-] Error: BM_KEY environment variable is required."
    exit 1
fi

mkdir -p /app/live

python3 -m brokenmirror.cli mount \
    -s /app/encrypted \
    -t /app/live \
    -m /app/matrix.key \
    -k "$BM_KEY" \
    --background

sleep 1

cd /app/live
exec "$@"