#!/usr/bin/env bash
# Send the emails Where Landlords Stand has left in its outbox, with the charity's shared mail.sh (in Where MPs
# Stand's checkout), which keeps the one copy of the server's mail password. Run on the server, as root:
#   bash /opt/wherelandlordsstand/deploy/send-mail.sh
# deploy/run-update.sh runs it after every weekly update. The site writes each email as a letter ("To:" and
# "Subject:" lines, a blank line, then the text) to /data/outbox in its data volume (src/landlords/notify.py); each
# letter sent is moved to outbox/sent/, where copies are kept for 30 days. A letter that can't be sent stays in the
# outbox for the next run, and this exits 1, so the unit that ran it fails and the server's alert says so.
set -uo pipefail
MAIL_SH="${MAIL_SH:-/opt/hansardgpt/deploy/mail.sh}"
DOCKER="${DOCKER:-docker}"
VOLUME="${VOLUME:-wherelandlordsstand_landlords-data}"   # the data volume: Compose names it after the project

if [[ -z "${OUTBOX:-}" ]]; then
  data=$($DOCKER volume inspect -f '{{ .Mountpoint }}' "$VOLUME") || {
    echo "✗ Can't find the site's data volume ($VOLUME): is the site installed (deploy/update.sh)?"; exit 1; }
  OUTBOX="$data/outbox"
fi

shopt -s nullglob
letters=("$OUTBOX"/*.txt)
if [[ ${#letters[@]} -eq 0 ]]; then
  echo "No emails waiting in the outbox."
  exit 0
fi
[[ -f "$MAIL_SH" ]] || { echo "✗ ${#letters[@]} email(s) waiting, but $MAIL_SH isn't there (Where MPs Stand's checkout)"; exit 1; }

mkdir -p "$OUTBOX/sent"
failed=0
for f in "${letters[@]}"; do
  # mail.sh skips a letter it has sent before (its name is in its sent log) and says so: either way it is done with
  if bash "$MAIL_SH" send "$f"; then
    mv -f "$f" "$OUTBOX/sent/"
  else
    echo "✗ $(basename "$f") was not sent: it stays in the outbox for the next run"
    failed=$((failed + 1))
  fi
done
find "$OUTBOX/sent" -name '*.txt' -type f -mtime +30 -delete

if [[ $failed -gt 0 ]]; then
  echo "✗ $failed email(s) not sent. Check the server's mail: bash $MAIL_SH test"
  exit 1
fi
