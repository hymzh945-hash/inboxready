"""Deterministic checks on one email: subject, spam triggers, links, attachments, MIME shape."""

from __future__ import annotations

import email
import math
import re
from collections import Counter
from email import policy
from pathlib import Path
from typing import Dict, List

WEIGHTS = {"high": 20.0, "medium": 8.0, "low": 2.0}
CAPS = {
    "missing_subject": 2,
    "subject_too_long": 2,
    "subject_shouting": 2,
    "subject_punctuation": 2,
    "spam_phrase": 6,
    "link_flood": 3,
    "link_text_mismatch": 3,
    "risky_attachment": 2,
    "attachment_unmentioned": 3,
    "phantom_attachment": 3,
    "html_only": 2,
    "image_heavy": 2,
    "no_unsubscribe": 2,
    "generic_greeting": 2,
    "shouting_body": 2,
    "reply_to_missing": 2,
    "long_paragraph": 3,
    "empty_body": 2,
}

SPAM_PHRASES = [
    "act now", "100% free", "risk-free", "risk free", "guaranteed", "guarantee you",
    "limited time", "click here", "buy now", "order now", "no cost", "no credit check",
    "unsecured", "work from home", "make money", "earn extra", "extra income",
    "lowest price", "best price", "congratulations", "winner", "you have been selected",
    "as seen on", "dear friend", "dear sir/madam", "to whom it may concern",
    "urgent response", "act immediately", "this is not spam", "not spam",
    "double your", "cash bonus", "serious cash", "trial offer", "special promotion",
    "once in a lifetime", "while supplies last", "no strings attached", "free gift",
    "satisfaction guaranteed", "millions", "billion", "viagra", "crypto giveaway",
]
URGENCY = ["now", "today", "immediately", "urgent", "last chance", "final", "deadline"]

RISKY_EXT = {".exe", ".scr", ".js", ".vbs", ".bat", ".cmd", ".jar", ".msi", ".com", ".pif"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".iso", ".img"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".txt"}

MONEY_RE = re.compile(r"(?:\$|usd|eur|gbp|\u00a5)\s?\d", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
LINK_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def _classes(tag: str) -> str:
    return " ".join(re.findall(r'class=["\']([^"\']+)', tag))


def _findings(check: str, severity: str, target: str, detail: str, page: int = 0, count: int = 1) -> List[Dict]:
    return [{"check": check, "severity": severity, "page": page, "target": target, "detail": detail}]


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", text or "")).strip()


class Mail:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser()
        if not self.path.exists():
            raise ValueError(f"file not found: {self.path}")
        raw = self.path.read_bytes()
        if self.path.suffix.lower() == ".msg":
            raise ValueError("Outlook .msg is a binary format. Save as .eml (or paste the draft as .txt).")
        try:
            self.message = email.message_from_bytes(raw, policy=policy.default)
        except Exception as exc:  # pragma: no cover - malformed input
            raise ValueError(f"cannot parse as an email: {exc}") from exc
        if not (self.message.get("Subject") is not None or self.message.get("From") is not None
                or self.path.suffix.lower() in (".eml", ".txt")):
            raise ValueError("this does not look like an .eml file (no Subject/From headers)")

        self.subject = str(self.message.get("Subject") or "")
        self.from_ = str(self.message.get("From") or "")
        self.to = str(self.message.get("To") or "")
        self.reply_to = str(self.message.get("Reply-To") or "")
        self.html = ""
        self.text = ""
        self.attachments: List[str] = []
        self.inline_images = 0
        self.multipart = self.message.is_multipart()

        parts = list(self.message.walk()) if self.multipart else [self.message]
        for part in parts:
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            filename = part.get_filename()
            if filename and "attachment" in disp.lower() or (filename and ctype not in ("text/plain", "text/html")):
                self.attachments.append(filename)
                continue
            if ctype == "text/html" and not self.html:
                try:
                    self.html = part.get_content()
                except Exception:
                    self.html = ""
            elif ctype == "text/plain" and not self.text:
                try:
                    self.text = part.get_content()
                except Exception:
                    self.text = ""
            if ctype.startswith("image/"):
                self.inline_images += 1

        body = self.html or self.text
        self.body_plain = _plain(body)
        self.links = LINK_RE.findall(self.html)


def check_subject(mail: Mail) -> List[Dict]:
    out = []
    if not mail.subject.strip():
        out += _findings("missing_subject", "high", "subject", "no subject line — most clients show the first body line instead")
        return out
    if len(mail.subject) > 60:
        out += _findings("subject_too_long", "medium", "subject",
                         f"{len(mail.subject)} characters; ~60 is where mobile clients cut it off")
    letters = [c for c in mail.subject if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        out += _findings("subject_shouting", "high", "subject",
                         f"subject is in caps: '{mail.subject[:50]}' — a standard spam signal")
    if re.search(r"[!?]{2,}", mail.subject) or len(EMOJI_RE.findall(mail.subject)) > 1:
        out += _findings("subject_punctuation", "medium", "subject",
                         "repeated !!/?? or several emoji in the subject")
    return out


def check_spam(mail: Mail) -> List[Dict]:
    hay = (mail.subject + " " + mail.body_plain).lower()
    hits = [p for p in SPAM_PHRASES if p in hay]
    out = []
    for hit in hits[:CAPS["spam_phrase"] + 2]:
        out += _findings("spam_phrase", "high", hit, f"trigger phrase in the copy: '{hit}'")
    return out


def check_links(mail: Mail) -> List[Dict]:
    out = []
    total = len(mail.links)
    if total > 4:
        out += _findings("link_flood", "medium", "links",
                         f"{total} links in one email — 3 or fewer is the practical limit before filters get interested")
    for href, label in mail.links:
        text = _plain(label)
        if not text or len(text) < 4:
            continue
        low = text.lower()
        if low.startswith("http") or "www." in low:
            continue
        if re.search(r"\bhere\b|\bclick\b|\blink\b", low):
            continue
        words = [w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 3]
        if words and words[0] not in href.lower():
            out += _findings("link_text_mismatch", "medium", text[:40],
                             f"text says '{text[:40]}' but points at {href[:60]} — rewrite the label or the link")
    return out


def check_attachments(mail: Mail) -> List[Dict]:
    out = []
    for name in mail.attachments:
        low = name.lower()
        ext = low[low.rfind("."):] if "." in low else ""
        if ext in RISKY_EXT:
            if low.count(".") >= 2:
                out += _findings("risky_attachment", "high", name,
                                 f"double extension ({ext} after a document extension) — "
                                 "reads as malware and gateways strip it")
            else:
                out += _findings("risky_attachment", "high", name,
                                 f"executable attachment ({ext}) — blocked or quarantined by most gateways")
        elif ext in ARCHIVE_EXT:
            out += _findings("risky_attachment", "medium", name,
                             "archive attachment — many corporate filters strip or quarantine it")

    says_attached = bool(re.search(r"\battach(ed|ment)?\b|\bsee attached\b|\benclosed\b", mail.body_plain, re.IGNORECASE))
    if says_attached and not mail.attachments and not mail.inline_images:
        out += _findings("phantom_attachment", "high", "body",
                         "the copy says a file is attached, but nothing is attached")
    if mail.attachments and not says_attached:
        out += _findings("attachment_unmentioned", "medium", "body",
                         f"{len(mail.attachments)} attachment(s) and the copy never mentions them — "
                         "readers and filters both treat that as unexpected")
    return out


def check_shape(mail: Mail) -> List[Dict]:
    out = []
    if mail.html and not mail.text:
        out += _findings("html_only", "medium", "mime",
                         "HTML with no text/plain part — some clients and filters penalise it")
    if mail.html:
        img_tags = len(re.findall(r"<img", mail.html, re.IGNORECASE))
        rendered = len(_plain(mail.html))
        if img_tags >= 2 and rendered < 400:
            out += _findings("image_heavy", "medium", "body",
                             f"{img_tags} images against {rendered} characters of text — classic image-only spam shape")
    marketing = bool(re.search(r"unsubscribe|opt[- ]out|manage (your )?preferences",
                               mail.html + " " + mail.body_plain, re.IGNORECASE))
    list_unsub = mail.message.get("List-Unsubscribe")
    promotional = (len(mail.links) >= 3 or len(re.findall(r"<img", mail.html, re.IGNORECASE)) >= 2
                   or any(p in (mail.subject + mail.body_plain).lower() for p in SPAM_PHRASES[:20]))
    if mail.html and promotional and not marketing and not list_unsub:
        out += _findings("no_unsubscribe", "medium", "headers",
                         "promotional HTML with no unsubscribe line and no List-Unsubscribe header")
    return out


def check_copy(mail: Mail) -> List[Dict]:
    out = []
    low = mail.body_plain.lower()
    for phrase in ("dear sir/madam", "to whom it may concern", "dear friend", "dear customer"):
        if phrase in low:
            out += _findings("generic_greeting", "low", phrase,
                             "generic greeting — it reads as a blast, and filters agree")
    letters = [c for c in mail.body_plain if c.isalpha()]
    if len(letters) >= 120 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        out += _findings("shouting_body", "medium", "body", "most of the body is in caps")
    if not mail.reply_to and "<" in mail.from_ and "@" in mail.from_:
        out += _findings("reply_to_missing", "low", "headers",
                         "no Reply-To header — replies go to the sending alias, not the person")
    for para in re.split(r"\n\s*\n|</p>", mail.text or mail.html):
        plain = _plain(para)
        if len(plain) > 500:
            out += _findings("long_paragraph", "low", "body",
                             f"a {len(plain)}-character paragraph — split it into three")
            break
    if not mail.body_plain.strip():
        out += _findings("empty_body", "high", "body", "the body is empty")
    urgency = sum(1 for w in URGENCY if re.search(r"\b%s\b" % w, low))
    if urgency >= 4:
        out += _findings("spam_phrase", "medium", "urgency",
                         f"{urgency} urgency words in one message (now/today/urgent/last chance)")
    return out


CHECKS = [check_subject, check_spam, check_links, check_attachments, check_shape, check_copy]


def score(findings: List[Dict]) -> Dict:
    penalty = 0.0
    per = Counter()
    for f in findings:
        cap = CAPS.get(f["check"], 2)
        per[f["check"]] += 1
        if per[f["check"]] <= cap:
            penalty += WEIGHTS.get(f["severity"], 2.0)
    value = 100 * math.exp(-penalty / 120)
    if value >= 85:
        verdict = "Ready to send"
    elif value >= 65:
        verdict = "Fix a few things first"
    else:
        verdict = "Likely landing in spam"
    return {"score": round(value, 1), "verdict": verdict, "penalty": round(penalty, 1)}


def audit(path: str | Path) -> Dict:
    mail = Mail(Path(path))
    findings = []
    for check in CHECKS:
        findings.extend(check(mail))
    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f["severity"]], f["check"]))
    sev = Counter(f["severity"] for f in findings)
    sc = score(findings)
    return {
        "doc": {
            "name": Path(path).name,
            "subject": mail.subject,
            "from": mail.from_,
            "to": mail.to,
            "attachments": mail.attachments,
            "links": len(mail.links),
            "words": len(re.findall(r"[A-Za-z0-9']+", mail.body_plain)),
            "html": bool(mail.html),
        },
        "findings": findings,
        "counts": dict(Counter(f["check"] for f in findings)),
        "severity": {k: sev.get(k, 0) for k in ("high", "medium", "low")},
        **sc,
    }


LABELS = {
    "missing_subject": ("no subject", "high"),
    "subject_too_long": ("subject too long", "medium"),
    "subject_shouting": ("caps subject", "high"),
    "subject_punctuation": ("!! in subject", "medium"),
    "spam_phrase": ("spam phrases", "high"),
    "link_flood": ("too many links", "medium"),
    "link_text_mismatch": ("link label mismatch", "medium"),
    "risky_attachment": ("risky attachment", "high"),
    "attachment_unmentioned": ("attachment unmentioned", "medium"),
    "phantom_attachment": ("phantom attachment", "high"),
    "html_only": ("html only", "medium"),
    "image_heavy": ("image heavy", "medium"),
    "no_unsubscribe": ("no unsubscribe", "medium"),
    "generic_greeting": ("generic greeting", "low"),
    "shouting_body": ("caps body", "medium"),
    "reply_to_missing": ("no reply-to", "low"),
    "long_paragraph": ("long paragraph", "low"),
    "empty_body": ("empty body", "high"),
}


def summary_rows(result: Dict) -> List[Dict]:
    return [{"check": LABELS[k][0], "count": result["counts"][k], "severity": LABELS[k][1], "key": k}
            for k in LABELS if result["counts"].get(k)]
