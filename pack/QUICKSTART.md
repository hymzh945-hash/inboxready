# InboxReady Pro — quickstart

Score an email draft before you hit send: subject caps and length, 40+ trigger phrases,
link count and label mismatch, risky or phantom attachments, HTML-only MIME shape.

18 deterministic checks. Zero dependencies. Nothing leaves your machine.

## 1. Install

```bash
pip install inboxready
```

Python 3.9+. No dependencies at all — stdlib only.

## 2. Activate Pro

Put the licence file we emailed you at either:

```bash
~/inboxready-license.json
# or
~/.inboxready/license.json
```

Or point at it explicitly:

```bash
export INBOXREADY_LICENSE=/path/to/inboxready-license.json
inboxready license
# Pro license · you@example.com · expires 2027-11-18
```

Verification is local (Ed25519, public key inside the package), so it works offline.

## 3. Audit a draft

Save the draft from your mail client as `.eml` (Outlook: File → Save As → Outlook Message
Format is `.msg`, which is binary — use "Save as .eml" via any IMAP client or paste the raw
source), then:

```bash
inboxready audit -i draft.eml --report review.html --csv findings.csv
```

- `review.html` — self-contained dark report: score, per-check counts, every finding with the
  exact phrase, attachment or link and what to change.
- `findings.csv` — severity, check, object, fix. One row per finding.

## 4. Learn it on two drafts

```bash
inboxready demo -o inboxready-demo
```

Writes `campaign_bad.eml` (scores 14, "Likely landing in spam") and `followup_good.eml`
(scores 100, "Ready to send"), audits both, and writes two reports. The spread is the point.

## What the score means

`100 * exp(-penalty / 120)`, severity-weighted, capped per check.

- **85+** — ready to send.
- **65–84** — fix a few things first.
- **below 65** — likely landing in spam.

## Checks included

missing_subject · subject_too_long · subject_shouting · subject_punctuation · spam_phrase ·
link_flood · link_text_mismatch · risky_attachment · phantom_attachment ·
attachment_unmentioned · html_only · image_heavy · no_unsubscribe · generic_greeting ·
shouting_body · reply_to_missing · long_paragraph · empty_body

## Limits, stated plainly

- Deterministic rules, not a deliverability oracle. Inbox placement also depends on domain
  reputation, SPF/DKIM/DMARC, sending volume and engagement. InboxReady never claims "this
  will reach the inbox" — it tells you what is visibly wrong with the draft.
- `.eml` or plain text only; `.msg` is binary, convert first.
- English phrase list. Non-English copy still gets the structural checks.
- HTML parsing is regex-based; ESP-templated mail with redirect links may read cleaner than
  the raw draft does.

## Support

Reply to the receipt email.
