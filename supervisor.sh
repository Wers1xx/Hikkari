#!/bin/bash
# Stable supervisor: restart only after 3 consecutive misses; log crashes
SESSION="hikka"
LOCK_FILE="/tmp/hikkari_supervisor.lock"
LOG="/tmp/hikkari_run.log"
MISS=0
MISS_NEED=3
INTERVAL=30

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -u +%FT%TZ)] another supervisor holds lock, exit" >> /tmp/supervisor.log
  exit 0
fi

is_running() {
  pgrep -f "[p]ython3 -m hikkari --root" >/dev/null 2>&1
}

start_hikka() {
  if is_running; then
    return 0
  fi
  rm -f /data/sessions/*.session-journal 2>/dev/null || true
  if ! is_running; then
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    sleep 1
  fi
  if is_running; then
    return 0
  fi
  : > "$LOG"
  tmux new-session -d -s "$SESSION"     "cd /root/Hikkari && . .venv/bin/activate && exec python3 -u -m hikkari --root >>$LOG 2>&1; echo EXIT:\$? >>$LOG"
  echo "[$(date -u +%FT%TZ)] started hikkari" >> /tmp/supervisor.log
  MISS=0
}

start_hikka

while true; do
  if is_running; then
    MISS=0
  else
    MISS=$((MISS+1))
    echo "[$(date -u +%FT%TZ)] miss=$MISS/$MISS_NEED" >> /tmp/supervisor.log
    if [ "$MISS" -ge "$MISS_NEED" ]; then
      echo "[$(date -u +%FT%TZ)] restarting after $MISS misses" >> /tmp/supervisor.log
      tail -c 2000 "$LOG" >> /tmp/supervisor.log 2>/dev/null || true
      start_hikka
      MISS=0
    fi
  fi
  sleep "$INTERVAL"
done
