# InboxReady

Score an email draft before you hit send.

InboxReady reads a `.eml` and reports the mechanical reasons a message lands in the promotions
tab, the spam folder, or a gateway quarantine — plus the embarrassing ones: the subject is in
caps, the copy says "see attached" and nothing is attached, the attachment is named
`invoice.pdf.exe`.

Zero dependencies. Stdlib only. Nothing leaves your machine, nothing is uploaded to a scoring
service, and no model is guessing at your tone.

## Install

```bash
pip install inboxready
```

Python 3.9+.

## Use

```bash
inboxready audit -i campaign_bad.eml
```

```
InboxReady 0.1.0 · campaign_bad.eml
  subject    ACT NOW!!! 100% FREE QUOTE INSIDE
  score      14/100  Likely landing in spam
  findings   23 (9 high, 12 medium, 2 low)
  shape      309 words · 5 links · 2 attachments
  - spam phrases            9  [high]
  - caps subject            1  [high]
  - risky attachment        2  [high]
  - too many links          1  [medium]
  - link label mismatch     4  [medium]
  - html only               1  [medium]
```

## Checks

| Check | What it catches | Severity |
|---|---|---|
| `missing_subject` | no subject line at all | high |
| `subject_too_long` | over 60 characters — cut off on mobile | medium |
| `subject_shouting` | subject mostly in caps | high |
| `subject_punctuation` | repeated `!!`/`??`, several emoji | medium |
| `spam_phrase` | 40+ trigger phrases, plus urgency-word clustering | high |
| `link_flood` | more than four links in one email | medium |
| `link_text_mismatch` | "Read the case study" pointing at `/a` — also an anti-phishing tell | medium |
| `risky_attachment` | `.exe/.js/.scr/…` or double extension (`invoice.pdf.exe`), archives | high / medium |
| `phantom_attachment` | copy says "attached", nothing attached | high |
| `attachment_unmentioned` | a file is attached and the copy never mentions it | medium |
| `html_only` | HTML with no `text/plain` alternative | medium |
| `image_heavy` | two or more images against very little text | medium |
| `no_unsubscribe` | promotional HTML without an unsubscribe line or `List-Unsubscribe` | medium |
| `generic_greeting` | "Dear Sir/Madam", "To whom it may concern" | low |
| `shouting_body` | most of the body in caps | medium |
| `reply_to_missing` | no `Reply-To` on a sending alias | low |
| `long_paragraph` | 500+ character paragraph walls | low |
| `empty_body` | empty body | high |

## Score

`100 * exp(-penalty / 120)`, severity-weighted, capped per check so one hundred spam phrases
do not drown out a missing subject. 85+ is "Ready to send", 65–84 is "Fix a few things first",
below 65 is "Likely landing in spam".

## Try it on two drafts

```bash
inboxready demo -o inboxready-demo
```

Writes a cold-outreach blast with every defect above and a clean client follow-up, audits both,
and generates `inboxready-campaign.html` and `inboxready-followup.html`. The clean one scores
100 and the blast scores 14 — that spread is the point.

## Free tier and Pro

Audit, score and the per-check summary are free.

Pro adds the HTML report, CSV export and the line-by-line fix list (which phrase, which
attachment, which link). Licence is a signed file verified offline (Ed25519, no server call).

```bash
inboxready audit -i draft.eml --report review.html --csv findings.csv
inboxready license
```

## Limits, stated plainly

- Rules are deterministic keyword and structure checks, not a deliverability oracle. Inbox
  placement also depends on domain reputation, SPF/DKIM/DMARC, sending volume and engagement.
- Never claims "this will reach the inbox". It tells you what is visibly wrong with the draft.
- `.eml` only (or plain text). Outlook `.msg` is a binary format — save as `.eml` first.
- English phrase list. Non-English copy gets the structural checks (links, attachments, MIME)
  but not the trigger-word pass.
- HTML analysis is regex-based; heavily templated mail from an ESP may hide links behind
  redirects and read cleaner than a plain draft does.

## Licence

Business source: free to use, including commercially, on your own drafts. Redistribution or
resale of the source requires a commercial licence. `LICENSE` holds the full text.
