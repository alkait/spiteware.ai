#!/usr/bin/env bash
# The unattended morning run on claude-pi, started daily by scripts/systemd/spite.timer.
#
# Pulls, runs /spite headless, then checks for itself that every app the run listed is on
# GitHub, on the live site and in a YouTube short. Silent when they are, or when nothing was
# listed; one email to the user when they are not. Logs go to
# ~/logs/spite/YYYY-MM-DD.log.
#
# Install (once, on claude-pi):
#   mkdir -p ~/.config/systemd/user
#   ln -sf "$PWD"/scripts/systemd/spite.{service,timer} ~/.config/systemd/user/
#   systemctl --user daemon-reload && systemctl --user enable --now spite.timer
#
# Everything sits inside main() so bash has read all of it before the pull can change this file.

main() {
    set -uo pipefail
    cd "$(dirname "$0")/.." || exit 1
    local day logs log
    day=$(date +%F)
    logs="$HOME/logs/spite"; mkdir -p "$logs"
    log="$logs/$day.log"
    exec >>"$log" 2>&1
    echo "=== $(date -Is) morning run"

    git pull --ff-only || { alert "git pull failed, so nothing ran today."; return 1; }

    timeout 4h claude -p "/spite" --dangerously-skip-permissions
    local code=$?
    echo "=== $(date -Is) claude exited $code"

    local listed
    listed=$(count < data/apps.json)
    if [ "$code" -ne 0 ] && [ "$listed" -eq 0 ]; then
        alert "the run crashed (exit $code) before listing anything."; return 1
    fi
    if [ ! -f "queue/raw-$day.json" ]; then
        alert "the sweep never ran, so nothing was found today."; return 1
    fi
    [ "$listed" -eq 0 ] && { echo "=== nothing listed today: done"; return 0; }

    local problems=()
    git fetch -q origin
    [ "$(git show origin/main:data/apps.json | count)" -ge "$listed" ] \
        || problems+=("the $listed new apps were not pushed to GitHub")

    # GitHub Pages can lag a push by a few minutes
    local live=0 i
    for i in $(seq 20); do
        live=$(curl -fsS "https://spiteware.ai/data/apps.json?t=$(date +%s)" | count)
        [ "${live:-0}" -ge "$listed" ] && break
        sleep 30
    done
    [ "${live:-0}" -ge "$listed" ] || problems+=("spiteware.ai is not serving today's apps")

    python3 -c "import json,sys;sys.exit('$day' not in json.load(open('shorts/.cache/uploaded.json')))" 2>/dev/null \
        || problems+=("today's short is not on YouTube")

    if [ ${#problems[@]} -gt 0 ]; then
        alert "$(IFS=';'; echo "${problems[*]}" | sed 's/;/; /g')."; return 1
    fi
    echo "=== all live: $listed apps, site and YouTube"
}

# How many apps in the apps.json on stdin were added today
count() {
    python3 -c "import json,sys,datetime;d=datetime.date.today().isoformat();print(sum(a.get('added')==d for a in json.load(sys.stdin)))" 2>/dev/null || echo 0
}

# One email to the user, through Claude's Gmail connector. (Claude Code's push notification
# won't do: in a headless run it thinks the user is watching the terminal and skips it.)
alert() {
    local msg="spiteware morning run $(date +%F) failed: $1 Log: ~/logs/spite/$(date +%F).log on claude-pi"
    echo "=== ALERT: $msg"
    echo "$msg" >> "$HOME/logs/spite/FAILED"
    timeout 5m claude -p "Send exactly one email with the Gmail send_message tool to alkait@gmail.com, subject: spiteware morning run failed, body: $msg — Do not do anything else." \
        --dangerously-skip-permissions --allowedTools mcp__claude_ai_Gmail__send_message \
        || echo "=== the alert email itself failed"
}

main "$@"; exit
