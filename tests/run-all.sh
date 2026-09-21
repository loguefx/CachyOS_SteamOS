#!/usr/bin/env bash
# Run every test. Nothing here touches your displays, your audio or Steam:
# the tests drive the logic with fakes, so they are safe mid-game.
set -uo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

failed=0
for suite in test-display.py test-watch.py test-audio.py test-hdmi-audio.py test-shortcut.py test-controllers.py; do
    printf '\n===== %s =====\n' "$suite"
    if ./"$suite" > /tmp/cachy-console-$suite.log 2>&1; then
        tail -1 /tmp/cachy-console-$suite.log
    else
        cat /tmp/cachy-console-$suite.log
        failed=$(( failed + 1 ))
    fi
done

printf '\n'
if (( failed )); then
    printf '%d suite(s) failed.\n' "$failed"
    exit 1
fi
printf 'All suites passed.\n'
