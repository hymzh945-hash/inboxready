"""`inboxready audit | demo | license`."""

from __future__ import annotations

import argparse
import csv
import sys
from email.message import EmailMessage
from pathlib import Path

from . import audit as audit_mod, licensing, report
from .version import __version__

URL = "https://hymz.gumroad.com/l/inboxready"


def _require_pro(feature: str) -> None:
    print(f"{feature} is part of InboxReady Pro — {URL}")
    raise SystemExit(1)


def build_demo(out: Path) -> tuple[Path, Path]:
    """Two emails that behave very differently in an inbox."""
    out.mkdir(parents=True, exist_ok=True)
    bad = out / "campaign_bad.eml"
    good = out / "followup_good.eml"

    m = EmailMessage()
    m["Subject"] = "ACT NOW!!! 100% FREE QUOTE INSIDE"
    m["From"] = "Quotes Team <quotes@example-mailer.com>"
    m["To"] = "procurement@example-buyer.com"
    m.set_content(
        "<html><body>"
        "<img src='https://example.com/banner.png'><img src='https://example.com/badge.png'>"
        "<p>Dear Sir/Madam,</p>"
        "<p>ACT IMMEDIATELY. Our LIMITED TIME offer is risk-free and guaranteed. "
        "This is not spam. Click here to buy now and double your margin today.</p>"
        "<p>See attached for the full price list.</p>"
        "<p><a href='https://example.com/a'>Read the case study</a> "
        "<a href='https://example.com/b'>Our pricing page</a> "
        "<a href='https://bit.ly/x1'>CLICK HERE</a> "
        "<a href='https://example.com/d'>Customer portal</a> "
        "<a href='https://example.com/e'>Partner program</a></p>"
        "<p>URGENT: last chance, deadline today.</p>"
        "</body></html>",
        subtype="html",
    )
    m.add_attachment(b"demo archive", maintype="application", subtype="zip", filename="pricing.zip")
    m.add_attachment(b"demo exe", maintype="application", subtype="octet-stream", filename="invoice.pdf.exe")
    m.set_type("multipart/mixed")
    bad.write_bytes(bytes(m))

    g = EmailMessage()
    g["Subject"] = "Q4 rollout deck — two open questions before Friday"
    g["From"] = "Mara Chen <mara@example-studio.com>"
    g["To"] = "dana@example-buyer.com"
    g["Reply-To"] = "mara@example-studio.com"
    g.set_content(
        "Hi Dana,\n\n"
        "Attached is the rollout deck we discussed on Tuesday. Two things I still need from you:\n\n"
        "1. Who signs off on the pilot budget?\n"
        "2. Do we start on the 4th or the 11th?\n\n"
        "Happy to jump on a call if that is faster.\n\nMara"
    )
    g.add_alternative(
        "<html><body><p>Hi Dana,</p>"
        "<p>Attached is the rollout deck we discussed on Tuesday. Two things I still need from you:</p>"
        "<ol><li>Who signs off on the pilot budget?</li><li>Do we start on the 4th or the 11th?</li></ol>"
        "<p>Happy to jump on a call if that is faster.</p><p>Mara</p></body></html>",
        subtype="html",
    )
    g.add_attachment(b"demo deck bytes", maintype="application", subtype="pdf", filename="rollout-deck.pdf")
    good.write_bytes(bytes(g))
    return bad, good


def cmd_audit(args: argparse.Namespace) -> int:
    pro = licensing.is_pro()
    result = audit_mod.audit(args.input)

    print(f"\nInboxReady {__version__} · {result['doc']['name']}")
    print(f"  subject    {result['doc']['subject'][:70] or '(none)'}")
    print(f"  score      {result['score']:.0f}/100  {result['verdict']}")
    print(f"  findings   {len(result['findings'])} "
          f"({result['severity'].get('high', 0)} high, "
          f"{result['severity'].get('medium', 0)} medium, "
          f"{result['severity'].get('low', 0)} low)")
    print(f"  shape      {result['doc']['words']} words · {result['doc']['links']} links · "
          f"{len(result['doc']['attachments'])} attachments")

    for row in audit_mod.summary_rows(result):
        print(f"  - {row['check']:<22} {row['count']:>3}  [{row['severity']}]")

    if args.csv:
        if not pro:
            _require_pro("CSV export")
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["severity", "check", "target", "detail"])
            writer.writeheader()
            for f in result["findings"]:
                writer.writerow({k: f[k] for k in writer.fieldnames})
        print(f"\nfindings -> {out}")

    if args.report:
        if not pro:
            _require_pro("HTML report")
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.build(result, pro=pro, version=__version__, top=args.top), "utf-8")
        print(f"report -> {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    bad, good = build_demo(out)
    pro = licensing.is_pro()

    for path in (bad, good):
        r = audit_mod.audit(path)
        print(f"{path.name}: {len(r['findings'])} findings · score {r['score']:.0f} · {r['verdict']}")
        for row in audit_mod.summary_rows(r):
            print(f"  - {row['check']}: {row['count']}")

    (out / "inboxready-campaign.html").write_text(
        report.build(audit_mod.audit(bad), pro=pro, version=__version__), "utf-8")
    (out / "inboxready-followup.html").write_text(
        report.build(audit_mod.audit(good), pro=pro, version=__version__), "utf-8")
    print(f"reports -> {out}/inboxready-campaign.html, {out}/inboxready-followup.html "
          f"({'Pro' if pro else 'free tier'})")
    return 0


def cmd_license(args: argparse.Namespace) -> int:
    st = licensing.status()
    if st["valid"]:
        print(f"Pro license · {st['email']} · expires {st['expires'] or 'lifetime'}")
        print(f"source: {licensing.license_path()}")
    else:
        print(f"Free tier · {st['info']}")
        print(f"Pro: {URL}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inboxready",
                                description="Score an email before you send it: subject, trigger words, links, attachments.")
    p.add_argument("--version", action="version", version=f"inboxready {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="audit one .eml draft")
    a.add_argument("-i", "--input", required=True)
    a.add_argument("--report", help="write an HTML report (Pro)")
    a.add_argument("--csv", help="write findings to CSV (Pro)")
    a.add_argument("--top", type=int, default=40)
    a.set_defaults(func=cmd_audit)

    d = sub.add_parser("demo", help="audit two bundled emails")
    d.add_argument("-o", "--out", default="inboxready-demo")
    d.set_defaults(func=cmd_demo)

    l = sub.add_parser("license", help="license status")
    l.set_defaults(func=cmd_license)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
