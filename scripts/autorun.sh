#!/usr/bin/env bash
# The unattended runs on claude-pi, started by the timers in scripts/systemd/:
#
#   autorun.sh daily     07:00 every day: /spite, then checks that every app it listed is on
#                        GitHub, on the live site and in a short on YouTube, TikTok and Instagram.
#   autorun.sh monthly   the 1st at 09:00: /spite monthly for last month, then checks that the
#                        episode is on YouTube and its script and Published line are on GitHub.
#
# Each run sends the user one Telegram message either way: the links when everything landed,
# what is missing when not.
# (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.)
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
    browser
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
    if [ "$listed" -eq 0 ]; then
        echo "=== nothing listed today: done"
        telegram "spiteware daily run $DAY: nothing new passed the gates, so nothing was posted."
        return 0
    fi

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
    [ -n "$(posted "$DAY" tiktok)" ] || problems+=("today's short is not on TikTok")
    [ -n "$(posted "$DAY" instagram)" ] || problems+=("today's short is not on Instagram")

    report "${problems[@]}" || return 1
    echo "=== all live: $listed apps, site, YouTube, TikTok and Instagram"
    telegram "spiteware daily run $DAY: $listed new apps, all live.
YouTube: https://youtube.com/shorts/$(uploaded "$DAY")
TikTok: $(posted "$DAY" tiktok)
Instagram: $(posted "$DAY" instagram)
Site: https://spiteware.ai/apps.html?sort=new"
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

    report "${problems[@]}" || return 1
    echo "=== the $month episode is up: https://youtube.com/watch?v=$video"
    telegram "spiteware monthly run: the $month episode is live.
YouTube: https://youtube.com/watch?v=$video"
}

# The YouTube id that scripts/upload.py noted for a date or a month, or nothing
uploaded() {
    python3 -c "import json,sys;print(json.load(open('shorts/.cache/uploaded.json')).get(sys.argv[1],''))" "$1" 2>/dev/null
}

# The post URL that scripts/handoff.py noted for a date and a platform, or nothing
posted() {
    python3 -c "import json,sys;print(json.load(open('shorts/.cache/posted.json')).get(sys.argv[1],{}).get(sys.argv[2],''))" "$1" "$2" 2>/dev/null
}

# Start the logged-in browser if it is down, in its own unit so it outlives this one: systemd
# ends everything a oneshot leaves behind, and the user needs it, and its VNC, after a failure.
browser() {
    curl -s http://127.0.0.1:9222/json/version >/dev/null && return 0
    systemd-run --user --unit=dev-browser --collect --setenv=PATH="$PATH" dev-browser
    local i
    for i in $(seq 30); do
        curl -s http://127.0.0.1:9222/json/version >/dev/null && return 0
        sleep 1
    done
    echo "=== the browser did not start"
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

# One Telegram message to the user. Plain curl, so it still arrives when Claude is what failed.
telegram() {
    curl -fsS -m 30 -o /dev/null "https://api.telegram.org/bot$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' .env)/sendMessage" \
        --data-urlencode "chat_id=$(sed -n 's/^TELEGRAM_CHAT_ID=//p' .env)" --data-urlencode "text=$1" \
        -d disable_web_page_preview=true \
        || echo "=== the Telegram message itself failed"
}

alert() {
    local msg="spiteware $MODE run $DAY failed: $1 Log: $LOG on claude-pi"
    echo "=== ALERT: $msg"
    echo "$msg" >> "$LOGS/FAILED"
    telegram "$msg"
}

main "$@"; exit
