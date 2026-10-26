#!/usr/bin/env bash
# The unattended runs on claude-pi, started by the timers in scripts/systemd/:
#
#   autorun.sh daily     07:00 every day: /spite, then checks that every app it listed is on
#                        GitHub, on the live site and in a YouTube short.
#   autorun.sh monthly   the 1st at 09:00: /spite monthly for last month, then checks that the
#                        episode is on YouTube and its script and Published line are on GitHub.
#
# Silent when everything landed (or the day listed nothing); one email to the user when not.
# Logs go to ~/logs/spite/YYYY-MM-DD[-monthly].log, failures also to ~/logs/spite/FAILED. The
# units hold a shared lock, so the two never run in the same checkout at once.
#
# Install (once, on claude-pi):
#   mkdir -p ~/.config/systemd/user ~/logs/spite
#   ln -sf "$PWD"/scripts/systemd/spite{,-monthly}.{service,timer} ~/.config/systemd/user/
#   systemctl --user daemon-reload && systemctl --user enable --now spite.timer spite-monthly.timer
#
# Everything sits inside main() so bash has read all of it before the pull can change this file.

main() {
    set -uo pipefail
    cd "$(dirname "$0")/.." || exit 1
    MODE=${1:-daily}
    DAY=$(date +%F)
    LOGS="$HOME/logs/spite"; mkdir -p "$LOGS"
    LOG="$LOGS/$DAY$([ "$MODE" = monthly ] && echo -monthly).log"
    exec >>"$LOG" 2>&1
    echo "=== $(date -Is) $MODE run"

    git pull --ff-only || { alert "git pull failed, so nothing ran."; return 1; }
    case "$MODE" in
        daily) daily ;;
        monthly) monthly ;;
        *) echo "unknown mode: $MODE"; return 2 ;;
    esac
}

daily() {
    timeout 4h claude -p "/spite" --dangerously-skip-permissions </dev/null
    local code=$?
    echo "=== $(date -Is) claude exited $code"

    local listed
    listed=$(count < data/apps.json)
    if [ "$code" -ne 0 ] && [ "$listed" -eq 0 ]; then
        alert "the run crashed (exit $code) before listing anything."; return 1
    fi
    if [ ! -f "queue/raw-$DAY.json" ]; then
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

    [ -n "$(uploaded "$DAY")" ] || problems+=("today's short is not on YouTube")

    report "${problems[@]}" && echo "=== all live: $listed apps, site and YouTube"
}

monthly() {
    local month
    month=$(python3 -c "import datetime;print((datetime.date.today().replace(day=1)-datetime.timedelta(days=1)).strftime('%Y-%m'))")
    if [ -n "$(uploaded "$month")" ]; then
        echo "=== the $month episode is already up: done"; return 0
    fi

    timeout 5h claude -p "/spite monthly $month" --dangerously-skip-permissions </dev/null
    local code=$?
    echo "=== $(date -Is) claude exited $code"

    local problems=() video
    video=$(uploaded "$month")
    [ -n "$video" ] || problems+=("the $month episode is not on YouTube (claude exited $code)")
    git fetch -q origin
    git cat-file -e "origin/main:episodes/$month.json" 2>/dev/null \
        || problems+=("episodes/$month.json was not pushed to GitHub")
    if [ -n "$video" ] && ! git show origin/main:episodes/ledger.md | grep -q "$video"; then
        problems+=("the ledger on GitHub has no Published line for $month")
    fi

    report "${problems[@]}" && echo "=== the $month episode is up: https://youtube.com/watch?v=$video"
}

# The YouTube id that scripts/upload.py noted for a date or a month, or nothing
uploaded() {
    python3 -c "import json,sys;print(json.load(open('shorts/.cache/uploaded.json')).get(sys.argv[1],''))" "$1" 2>/dev/null
}

# How many apps in the apps.json on stdin were added today
count() {
    python3 -c "import json,sys,datetime;d=datetime.date.today().isoformat();print(sum(a.get('added')==d for a in json.load(sys.stdin)))" 2>/dev/null || echo 0
}

# Alert with every problem given, if any; succeed only when there were none
report() {
    [ $# -eq 0 ] && return 0
    alert "$(printf '%s; ' "$@" | sed 's/; $//')."
    return 1
}

# One email to the user, through Claude's Gmail connector. (Claude Code's push notification
# won't do: in a headless run it thinks the user is watching the terminal and skips it.)
alert() {
    local msg="spiteware $MODE run $DAY failed: $1 Log: $LOG on claude-pi"
    echo "=== ALERT: $msg"
    echo "$msg" >> "$LOGS/FAILED"
    timeout 5m claude -p "Send exactly one email with the Gmail send_message tool to alkait@gmail.com, subject: spiteware $MODE run failed, body: $msg — Do not do anything else." \
        --dangerously-skip-permissions --allowedTools mcp__claude_ai_Gmail__send_message </dev/null \
        || echo "=== the alert email itself failed"
}

main "$@"; exit
