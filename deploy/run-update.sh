#!/usr/bin/env bash
# The weekly update, as landlords-update.service runs it, and as it is run by hand. Run on the server, as root:
#   bash /opt/wherelandlordsstand/deploy/run-update.sh
# It runs `landlords update` in a one-off container, then sends the email the update left in the outbox
# (deploy/send-mail.sh, through the shared mail.sh). It exits 1 if the update needs attention or the email wasn't
# sent, so the unit fails and the server's alert says so. Extra arguments go to `landlords update` (--no-fetch, say).
set -uo pipefail
DIR="${DIR:-/opt/wherelandlordsstand}"
DOCKER="${DOCKER:-docker}"
# One update at a time on the whole server: every site's update takes the same lock, and this one waits for any other
# to finish rather than fail (Where MPs Stand's sync can take up to 6 hours).
LOCK="${LOCK:-/var/lock/wheretheystand-update.lock}"

cd "$DIR/deploy" || exit 1
flock "$LOCK" $DOCKER compose run --rm -T app landlords update "$@"
rc=$?
# Sent even when the update needs attention: the email says what.
if ! bash "$DIR/deploy/send-mail.sh"; then
  echo "✗ The update's email was not sent"
  rc=1
fi
exit $rc
