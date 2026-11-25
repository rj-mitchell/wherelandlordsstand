# Letters

Letters to outside bodies on the site's behalf. Whether each has been sent, and any reply, is logged in the charity's
correspondence log (`family/LETTERS.md` in its repository). Each letter starts with its To: and Subject: lines (and
Cc: if wanted), and is sent from the charity's account by Where MPs Stand's `deploy/mail.sh` (its `docs/HOSTING.md`,
"Email from the server"):

    bash /opt/hansardgpt/deploy/mail.sh send --test-to <a test address> /opt/wherelandlordsstand/outreach/2026-11/ombudsman.txt
    bash /opt/hansardgpt/deploy/mail.sh send /opt/wherelandlordsstand/outreach/2026-11/ombudsman.txt

The first sends a test copy only; the second sends it for real. A letter already sent is skipped. Replies arrive in
the account's inbox; the Ombudsman's answer goes into docs/DECISIONS.md, decision 9.
