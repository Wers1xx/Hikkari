#!/bin/bash
# Single-process supervisor for Hikkari (no session race)
SESSION="hikka"
LOCK_FILE="/tmp/hikkari_supervisor.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -u +%FT%TZ)] another supervisor holds lock, exit"
  exit 0
fi

start_hikka() {
  if pgrep -f "python3 -m hikkari --root" >/dev/null 2>&1; then
    return 0
  fi
  # drop stale sqlite journals so lock clears after crash
  rm -f /data/sessions/*.session-journal /root/Hikkari/*.session-journal 2>/dev/null || true
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  sleep 1
  tmux new-session -d -s "$SESSION" \
    "cd /root/Hikkari && . .venv/bin/activate && exec python3 -m hikkari --root"
  echo "[$(date -u +%FT%TZ)] started hikkari in tmux session $SESSION"
}

# boot once immediately
start_hikka

while true; do
  if ! pgrep -f "python3 -m hikkari --root" >/dev/null 2>&1; then
    echo "[$(date -u +%FT%TZ)] hikkari process not found, restarting"
    start_hikka
  fi
  sleep 20
done
