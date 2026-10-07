"""
Shared branded HTML email template for every investor-facing email.

Every email the app actually sends funnels through one of two send points —
_send_pending_email_now() in app/Investments/route.py (the real one;
MANUAL_EMAIL_APPROVAL defaults to True in every config, so this is the only
path actually exercised) and EmailService._send_email_immediately() in
app/utils/email_service.py (kept in sync for when/if that config is ever
flipped). Both previously wrapped the plain-text body in a bare, unbranded
<p>/<ul> HTML shell. This module replaces that shell with the AXYS INVESTMENT BANK
card layout: logo header, title banner, styled body, footer — reusing the
brand navy from app/utils/statement_theme.py so emails match the PDF
statements clients also receive.

The body text itself is unchanged (still built ad hoc in email_service.py /
route.py) — this module only re-renders it as HTML: paragraphs become <p>,
"•"/"*" lines become <ul><li>, and a short ALL-CAPS line on its own (e.g.
"DEPLOYMENT SUMMARY") becomes a section sub-heading. No box/table treatment
for individual fields — kept intentionally simple per product decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape as _escape
from pathlib import Path
from typing import Optional

BRAND_NAVY = "#00005b"
LOGO_CONTENT_ID = "axys_logo_header"

# Maps PendingEmail.email_type -> the title banner text shown under the logo.
# Falls back to a title-cased version of the email_type itself if not listed.
EMAIL_TITLES = {
    "DEPOSIT_CONFIRMATION": "Deposit Confirmation",
    "OFFSHORE_TRANSFER": "Transfer Confirmation",
    "INVESTMENT_ACTIVE": "Deployment Confirmation",
    "INVESTMENT_ACTIVE_OVERSUBSCRIBED": "Deployment Confirmation — Pro-Rata Allocation",
    "INVESTOR_STATEMENT": "Statement Ready",
    "WITHDRAWAL_RECEIVED": "Withdrawal Request Received",
    "WITHDRAWAL_APPROVED": "Withdrawal Approved",
    "BATCH_UPLOAD": "Batch Notification",
}


def get_email_title(email_type: Optional[str], fallback: str = "Notification") -> str:
    if not email_type:
        return fallback
    if email_type in EMAIL_TITLES:
        return EMAIL_TITLES[email_type]
    return email_type.replace("_", " ").title()


def get_axys_logo_bytes() -> Optional[bytes]:
    """Reuses the same logo file resolution already used for PDF statements."""
    try:
        from app.utils.statement_theme import resolve_axys_logo_path
        path = resolve_axys_logo_path()
        if path and path.exists():
            return path.read_bytes()
    except Exception:
        pass
    return None


def _render_body_html(text: str) -> str:
    safe = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in safe.split("\n\n") if p.strip()]

    parts = []
    for para in paragraphs:
        lines = [line.strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue

        # A single short ALL-CAPS line on its own is a section sub-heading
        # (e.g. "DEPLOYMENT SUMMARY", "REFUND") — not a bulleted/plain line.
        if len(lines) == 1 and lines[0].isupper() and len(lines[0]) <= 60:
            parts.append(
                f'<p style="margin:24px 0 8px 0;color:{BRAND_NAVY};font-size:12px;'
                f'font-weight:700;letter-spacing:0.8px;text-transform:uppercase;'
                f'border-bottom:1px solid #e5e7eb;padding-bottom:6px;">{_escape(lines[0])}</p>'
            )
            continue

        if any(line.startswith("•") or line.startswith("*") for line in lines):
            items = []
            for line in lines:
                clean = line[1:].strip() if line.startswith(("•", "*")) else line
                if clean:
                    items.append(f'<li style="margin:4px 0;font-size:14px;line-height:1.5;">{_escape(clean)}</li>')
            parts.append(f'<ul style="margin:8px 0;padding-left:22px;">{"".join(items)}</ul>')
            continue

        para_html = "<br/>".join(_escape(line) for line in lines)
        parts.append(f'<p style="margin:12px 0;font-size:14px;line-height:1.6;color:#333333;">{para_html}</p>')

    return "".join(parts)


def render_branded_email_html(title: str, body_text: str) -> str:
    """Wraps body_text (plain text) in the branded card layout as an HTML string."""
    year = datetime.now(timezone.utc).year
    body_html = _render_body_html(body_text)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f5f8;font-family:'Segoe UI',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f8;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
<tr><td style="height:4px;background-color:{BRAND_NAVY};line-height:4px;font-size:0;">&nbsp;</td></tr>
<tr><td style="padding:32px 40px 12px 40px;text-align:center;">
<img src="cid:{LOGO_CONTENT_ID}" alt="AXYS INVESTMENT BANK" width="150" style="display:block;margin:0 auto;height:auto;border:0;">
</td></tr>
<tr><td style="padding:0 40px 24px 40px;text-align:center;">
<p style="margin:0;color:{BRAND_NAVY};font-size:13px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;">{_escape(title)}</p>
</td></tr>
<tr><td style="padding:0 40px 8px 40px;">
{body_html}
</td></tr>
<tr><td style="padding:28px 40px 24px 40px;border-top:1px solid #eeeeee;text-align:center;">
<p style="margin:0;color:#9aa0ab;font-size:11px;">&copy; {year} AXYS INVESTMENT BANK. All rights reserved.</p>
<p style="margin:6px 0 0 0;color:#9aa0ab;font-size:11px;">The Promenade, 5th Floor, General Mathenge Rd, Nairobi, Kenya</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def attach_brand_logo(msg) -> bool:
    """
    Attaches the AXYS logo to a flask_mail.Message as an inline (CID) image so
    render_branded_email_html()'s <img src="cid:..."> resolves in the client's
    inbox. Returns True if attached, False if the logo file couldn't be found
    (email still sends fine — just without the header image).
    """
    logo_bytes = get_axys_logo_bytes()
    if not logo_bytes:
        return False
    msg.attach(
        filename="axys-logo.png",
        content_type="image/png",
        data=logo_bytes,
        disposition="inline",
        headers={"Content-ID": f"<{LOGO_CONTENT_ID}>"},
    )
    return True
