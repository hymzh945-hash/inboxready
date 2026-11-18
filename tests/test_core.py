"""InboxReady behaviour tests — the checks must fire on the bundled bad draft."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from inboxready import audit, report
from inboxready.cli import build_demo
from inboxready.licensing import PRODUCT


def _mail(subject: str, body: str, *, html: bool = False, attachments=(), from_="A <a@example.com>"):
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = from_
    m["To"] = "b@example.com"
    if html:
        m.set_content(body, subtype="html")
    else:
        m.set_content(body)
    for name, payload in attachments:
        m.add_attachment(payload, maintype="application", subtype="octet-stream", filename=name)
    return bytes(m)


def test_product_name_is_the_licence_scope():
    assert PRODUCT == "inboxready"


def test_demo_campaign_is_badly_flagged(tmp_path):
    bad, good = build_demo(tmp_path)
    result = audit.audit(bad)
    names = {f["check"] for f in result["findings"]}
    for expected in {"subject_shouting", "subject_punctuation", "spam_phrase", "link_flood",
                     "link_text_mismatch", "risky_attachment", "html_only", "image_heavy",
                     "generic_greeting"}:
        assert expected in names, f"{expected} did not fire"
    assert result["score"] < 40
    assert result["verdict"] == "Likely landing in spam"


def test_demo_followup_is_clean(tmp_path):
    _, good = build_demo(tmp_path)
    result = audit.audit(good)
    assert result["findings"] == [], f"clean email flagged: {result['findings']}"
    assert result["score"] == 100
    assert result["verdict"] == "Ready to send"


def test_double_extension_is_high_severity(tmp_path):
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Quarterly numbers", "Please see the file.", attachments=[("invoice.pdf.exe", b"x")]))
    result = audit.audit(path)
    hit = [f for f in result["findings"] if f["check"] == "risky_attachment"]
    assert hit and hit[0]["severity"] == "high"
    assert "double extension" in hit[0]["detail"]


def test_archive_attachment_is_medium(tmp_path):
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Files", "Attached the archive.", attachments=[("pricing.zip", b"x")]))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "risky_attachment"]
    assert hit and hit[0]["severity"] == "medium"


def test_phantom_attachment(tmp_path):
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Deck", "The deck is attached, see attached."))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "phantom_attachment"]
    assert hit and hit[0]["severity"] == "high"
    assert "nothing is attached" in hit[0]["detail"]


def test_attachment_never_mentioned(tmp_path):
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Numbers", "Here are the numbers you asked about.",
                           attachments=[("q3.pdf", b"x")]))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "attachment_unmentioned"]
    assert hit and hit[0]["severity"] == "medium"


def test_link_label_mismatch(tmp_path):
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Case study", "<p><a href='https://example.com/a'>Read the case study</a></p>",
                           html=True))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "link_text_mismatch"]
    assert hit and "Read the case study" in hit[0]["detail"]


def test_link_flood(tmp_path):
    body = "".join(f"<p><a href='https://example.com/{i}'>link {i} here</a></p>" for i in range(6))
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Options", body, html=True))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "link_flood"]
    assert hit and "6 links" in hit[0]["detail"]


def test_good_promotional_mail_needs_unsubscribe(tmp_path):
    body = ("<p><a href='https://example.com/a'>Prices</a> "
            "<a href='https://example.com/b'>Plans</a> "
            "<a href='https://example.com/c'>Contact</a></p>")
    path = tmp_path / "m.eml"
    path.write_bytes(_mail("Our new plans", body, html=True))
    hit = [f for f in audit.audit(path)["findings"] if f["check"] == "no_unsubscribe"]
    assert hit


def test_rejects_msg(tmp_path):
    path = tmp_path / "draft.msg"
    path.write_bytes(b"\xd0\xcf\x11\xe0binary")
    with pytest.raises(ValueError):
        audit.audit(path)


def test_report_free_tier_locks_findings(tmp_path):
    bad, _ = build_demo(tmp_path)
    result = audit.audit(bad)
    free = report.build(result, pro=False)
    assert "Line-by-line fixes are Pro" in free
    paid = report.build(result, pro=True)
    assert "spam_phrase" in paid and "Line-by-line fixes are Pro" not in paid


def test_summary_rows_add_up(tmp_path):
    bad, _ = build_demo(tmp_path)
    result = audit.audit(bad)
    rows = audit.summary_rows(result)
    assert sum(r["count"] for r in rows) == len(result["findings"])
