#!/usr/bin/env bash
# Run all gantt_studio JS tests.
# Requires: node 18+, @xmldom/xmldom (auto-installed in /tmp on first run).
set -euo pipefail

cd "$(dirname "$0")"

# Install xmldom in /tmp once for arch-string tests.
if [ ! -d /tmp/node_modules/@xmldom ]; then
    echo "→ Installing @xmldom/xmldom in /tmp (one-time)…"
    (cd /tmp && npm install --no-save --silent @xmldom/xmldom)
fi
# Make /tmp's node_modules visible to test_utils.mjs
export NODE_PATH=/tmp/node_modules

PASS=0
FAIL=0
for t in test_utils.mjs test_renderer.mjs; do
    echo
    echo "════════════════════════════════════════════════════════════════════════"
    echo "▶ $t"
    echo "════════════════════════════════════════════════════════════════════════"
    if node "$t"; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
done

echo
echo "════════════════════════════════════════════════════════════════════════"
echo "OVERALL: $PASS suite(s) passed, $FAIL failed"
echo "════════════════════════════════════════════════════════════════════════"
exit $FAIL
