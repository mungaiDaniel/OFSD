"""
Bulk "send one type of email to a whole fund/batch" for the Email page's Send Statements tab.

Types (kind -> email_type): deposit, transfer, deployment, withdrawal, oversubscription.
(The "overall statement" kind keeps its own queue-batch endpoint.)

Safety rules - this module exists because one "Confirm All" once sent 125 unrelated emails:
  * A send is always scoped to ONE explicit selection (kind + fund and/or batch). It never
    touches pending emails outside that selection.
  * The caller previews first and passes the previewed count back as expected_count; if the
    server now computes a different number, nothing is queued (409) and the user must preview again.
  * Nothing is sent from here. Rows are only marked 'Queued'; the throttled drain scheduler
    (email_queue_scheduler_service) sends them 100 per interval.
  * Investors who already received that email are skipped unless include_sent is set.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.database.database import db
from app.Investments.model import Investment, PendingEmail, Withdrawal

logger = logging.getLogger(__name__)

MAX_TARGETS = 5000

KINDS: Dict[str, Dict[str, Any]] = {
    "deposit": {"label": "Deposit confirmation", "types": ("DEPOSIT_CONFIRMATION",)},
    "transfer": {"label": "Transfer confirmation", "types": ("OFFSHORE_TRANSFER",)},
    "deployment": {"label": "Deployment confirmation", "types": ("INVESTMENT_ACTIVE",)},
    "withdrawal": {"label": "Withdrawal notice", "types": ("WITHDRAWAL_RECEIVED", "WITHDRAWAL_APPROVED")},
    "oversubscription": {"label": "Oversubscription / refund notice", "types": ("OVERSUBSCRIPTION_REFUND_NOTICE",)},
}

ACTIVE = ("Queued", "Sending")
REQUEUEABLE = ("Pending_Confirmation", "Suppressed", "Failed")
_APPROVED_WITHDRAWAL = ("Approved", "Processed", "Completed", "Executed")


class BulkEmailError(Exception):
    def __init__(self, message: str, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def _f(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


# --------------------------------------------------------------------- bodies
def _deposit_content(inv: Investment, batch: Batch):
    currency = inv.currency_type or "USD"
    name = inv.investor_name or "Investor"
    subject = f"Deposit Received - {batch.batch_name}"
    body = f"""Dear {name},

We have successfully received your investment deposit into batch \"{batch.batch_name}\".

Deposit details
• Capital Amount: {currency} {_f(inv.amount_deposited):,.2f}
• Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will receive a follow-up email once the transfer has been initiated.

Please find the attached deposit statement for your records.

Best regards,
AXYS INVESTMENT BANK

"""
    return subject, body, currency


def _transfer_content(inv: Investment, batch: Batch):
    from app.utils.statement_theme import is_dangote_dprp_fund

    currency = inv.currency_type or "USD"
    name = inv.investor_name or "Investor"
    fund = getattr(inv, "fund", None)
    label = "Shares" if is_dangote_dprp_fund(
        [getattr(fund, "fund_name", None)], [getattr(fund, "fund_code", None)]
    ) else "Fund"
    subject = f"Funds Successfully Transferred to {label} - {batch.batch_name}"
    body = f"""Dear {name},

We are pleased to inform you that your funds in batch "{batch.batch_name}" have been successfully transferred to our offshore investment partner.

Status: Transferred (Stage 2/3)

The funds are now awaiting final deployment into the active portfolio. We will notify you once the deployment is confirmed and your returns begin to accrue.

Initial Deposit: {currency} {_f(inv.amount_deposited):,.2f}
Allocated Transaction Fee: -{currency} {_f(inv.transfer_fee_deducted):,.2f}
Allocated Entry Fee: -{currency} {_f(inv.deployment_fee_deducted):,.2f}
New Active Balance: {currency} {_f(inv.net_principal):,.2f}

Best regards,
AXYS INVESTMENT BANK

"""
    return subject, body, currency


def _deployment_content(inv: Investment, batch: Batch):
    currency = inv.currency_type or "USD"
    name = inv.investor_name or "Investor"
    deployment_nav = _f(getattr(batch, "deployment_nav", 0))
    from app.utils.deployment_date import resolve_client_deployment_date
    _dd = resolve_client_deployment_date([inv], batch)
    deploy_date = (_dd or datetime.now()).strftime("%Y-%m-%d")
    original = _f(inv.amount_deposited)
    transfer_fee = _f(inv.transfer_fee_deducted)
    entry_fee = _f(inv.deployment_fee_deducted)
    total_fees = transfer_fee + entry_fee
    net_amount = original - total_fees
    shares = _f(inv.shares_owned) if inv.shares_owned is not None else None
    nav = _f(inv.previous_nav_price or deployment_nav) if (inv.previous_nav_price is not None or deployment_nav) else None
    nav_lines = ""
    if shares is not None and nav is not None and nav > 0:
        nav_lines = f"""
Shares: {shares:,.4f}
NAV / Share: {nav:,.6f}"""
    subject = f"Funds Successfully Deployed: {batch.batch_name}"
    body = f"""Dear {name},

Your investment in {batch.batch_name} has been successfully deployed and is now ACTIVE.

DEPLOYMENT SUMMARY

Original Deposit Amount: {currency} {original:,.2f}
Transaction Fee Contribution: -{currency} {transfer_fee:,.2f}
Entry Fee Contribution: -{currency} {entry_fee:,.2f}
Total Fees: -{currency} {total_fees:,.2f}
Net Deployed Amount: {currency} {net_amount:,.2f}{nav_lines}

Deployment Date: {deploy_date}
Status: Active (Stage 3/3)

Thank you for investing with AXYS INVESTMENT BANK.

Best regards,
AXYS INVESTMENT BANK
"""
    return subject, body, currency


# -------------------------------------------------------------------- targets
def _target(**kw) -> Dict[str, Any]:
    kw.setdefault("batch_id", None)
    kw.setdefault("batch_name", None)
    kw.setdefault("amount", None)
    kw.setdefault("withdrawal_id", None)
    return kw


def collect_targets(kind: str, fund_id: Optional[int], batch_id: Optional[int], client_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Targets for the selection; client_code narrows it to ONE investor (per-row send again / preview)."""
    targets = _collect_targets(kind, fund_id, batch_id)
    code = (client_code or "").strip().lower()
    if code:
        targets = [t for t in targets if str(t.get("client_code") or "").strip().lower() == code]
    return targets


def _collect_targets(kind: str, fund_id: Optional[int], batch_id: Optional[int]) -> List[Dict[str, Any]]:
    if kind not in KINDS:
        raise BulkEmailError(f"Unknown statement type '{kind}'")
    if fund_id is None and batch_id is None:
        raise BulkEmailError("Choose a fund or a batch")

    if kind in ("deposit", "transfer", "deployment"):
        return _investment_targets(kind, fund_id, batch_id)
    if kind == "withdrawal":
        return _withdrawal_targets(fund_id, batch_id)
    return _oversubscription_targets(fund_id, batch_id)


def _investment_targets(kind, fund_id, batch_id):
    q = (
        db.session.query(Investment, Batch)
        .join(Batch, Investment.batch_id == Batch.id)
    )
    if batch_id is not None:
        q = q.filter(Batch.id == batch_id)
    if fund_id is not None:
        q = q.filter(Investment.fund_id == fund_id)
    if kind == "transfer":
        q = q.filter(Batch.is_transferred.is_(True))
    elif kind == "deployment":
        q = q.filter(Batch.deployment_confirmed.is_(True))
    q = q.order_by(Batch.id, Investment.investor_name, Investment.id).limit(MAX_TARGETS + 1)

    build = {"deposit": _deposit_content, "transfer": _transfer_content, "deployment": _deployment_content}[kind]
    email_type = KINDS[kind]["types"][0]
    out = []
    for inv, batch in q.all():
        subject, body, currency = build(inv, batch)
        fund = getattr(inv, "fund", None)
        out.append(_target(
            investor_id=inv.id, client_code=inv.internal_client_code, name=inv.investor_name or "Investor",
            email=(inv.investor_email or "").strip(), fund_name=getattr(fund, "fund_name", None),
            batch_id=batch.id, batch_name=batch.batch_name, amount=_f(inv.amount_deposited),
            currency=currency, email_type=email_type, subject=subject, body=body,
        ))
    return out


def _investment_for(code: str, fund_id, batch_id=None) -> Optional[Investment]:
    q = db.session.query(Investment).filter(func.lower(Investment.internal_client_code) == (code or "").lower())
    if fund_id is not None:
        q = q.filter(Investment.fund_id == fund_id)
    if batch_id is not None:
        found = q.filter(Investment.batch_id == batch_id).first()
        if found:
            return found
    return q.order_by(Investment.id).first()


def _withdrawal_targets(fund_id, batch_id):
    q = db.session.query(Withdrawal).filter(
        Withdrawal.source != "oversubscription_refund", Withdrawal.status != "Rejected"
    )
    if fund_id is not None:
        q = q.filter(Withdrawal.fund_id == fund_id)
    if batch_id is not None:
        q = q.filter(Withdrawal.batch_id == batch_id)
    out = []
    for w in q.order_by(Withdrawal.date_withdrawn.desc(), Withdrawal.id).limit(MAX_TARGETS + 1).all():
        inv = _investment_for(w.internal_client_code, w.fund_id, w.batch_id)
        if inv is None:
            continue
        approved = w.status in _APPROVED_WITHDRAWAL
        currency = inv.currency_type or "USD"
        name = inv.investor_name or "Investor"
        fund_name = (w.fund.fund_name if getattr(w, "fund", None) else w.fund_name) or "your fund"
        amount = _f(w.amount)
        if approved:
            email_type, subject = "WITHDRAWAL_APPROVED", f"Withdrawal Approved - {fund_name}"
            # A unit redemption (from the transfer agent's contract note) also
            # states the shares sold, the price and the trade date.
            redemption_lines = ""
            if w.shares_redeemed is not None:
                lines = [f"Shares Redeemed: {_f(w.shares_redeemed):,.4f} at NAV {_f(w.redemption_nav):,.4f}"]
                if w.trade_date:
                    lines.append(f"Trade Date: {w.trade_date.strftime('%d %B %Y')}")
                lines.append(f"Gross Amount: {currency} {_f(w.gross_amount):,.2f}")
                if _f(w.exit_fee_deducted):
                    lines.append(f"Exit Fee: {currency} {_f(w.exit_fee_deducted):,.2f}")
                redemption_lines = "\n".join(lines) + "\n"
            body = f"""Dear {name},

We are pleased to inform you that your withdrawal request has been APPROVED.

Client Code: {w.internal_client_code}
{redemption_lines}Approved Amount: {currency} {amount:,.2f}
Status: Approved / Scheduled for Distribution

Please find attached your withdrawal statement for your records.

The funds will be processed according to the standard distribution timeline. Thank you for your continued partnership with AXYS INVESTMENT BANK.

Best regards,
AXYS INVESTMENT BANK

"""
        else:
            email_type, subject = "WITHDRAWAL_RECEIVED", f"Withdrawal Request Received - {fund_name}"
            body = f"""Dear {name},

This is to confirm that we have received your withdrawal request for your investment in {fund_name}.

Client Code: {w.internal_client_code}
Withdrawal Amount: {currency} {amount:,.2f}
Status: Received / Processing

Our team is currently reviewing your request. You will receive a follow-up notification once the withdrawal is approved and scheduled for distribution. Your withdrawal statement is attached for your records.

Best regards,
AXYS INVESTMENT BANK

"""
        out.append(_target(
            investor_id=inv.id, client_code=w.internal_client_code, name=name,
            email=(inv.investor_email or "").strip(), fund_name=fund_name,
            amount=amount, currency=currency, email_type=email_type, subject=subject, body=body,
            withdrawal_id=w.id,
        ))
    return out


def _oversubscription_targets(fund_id, batch_id):
    from app.Investments.route import _get_oversubscription_refund_context

    q = db.session.query(Withdrawal).filter(Withdrawal.source == "oversubscription_refund")
    if fund_id is not None:
        q = q.filter(Withdrawal.fund_id == fund_id)
    if batch_id is not None:
        q = q.filter(Withdrawal.batch_id == batch_id)
    out = []
    for w in q.order_by(Withdrawal.id).limit(MAX_TARGETS + 1).all():
        inv = _investment_for(w.internal_client_code, w.fund_id, w.batch_id)
        if inv is None or inv.fund_id is None:
            continue
        ctx = _get_oversubscription_refund_context(inv.internal_client_code, inv.fund_id)
        if ctx is None:
            continue
        batch = db.session.get(Batch, w.batch_id) if w.batch_id else db.session.get(Batch, inv.batch_id)
        batch_name = batch.batch_name if batch else "your batch"
        name = inv.investor_name or "Investor"
        subject = f"Oversubscription / Refund Notice: {batch_name}"
        body = f"""Dear {name},

{batch_name} was oversubscribed — total investor commitments exceeded what could actually be deployed into shares. As a result, part of your deposit was not deployed and is being refunded.

Amount Deployed Into Shares: {ctx['currency']} {float(ctx['total_deployed']):,.2f}
Refund Amount: {ctx['currency']} {float(ctx['total_refund']):,.2f}
Refund Status: {ctx['refund_status']}

Your refund is processed through our standard withdrawal approval flow. You will receive a separate notification once it is approved and scheduled for payout. This is a one-time notice for this deployment — it will not be repeated on future statements.

Best regards,
AXYS INVESTMENT BANK
"""
        t = _target(
            investor_id=inv.id, client_code=inv.internal_client_code, name=name,
            email=(inv.investor_email or "").strip(),
            fund_name=getattr(getattr(inv, "fund", None), "fund_name", None),
            batch_id=batch.id if batch else None, batch_name=batch_name, amount=_f(ctx["total_refund"]),
            currency=ctx["currency"], email_type="OVERSUBSCRIPTION_REFUND_NOTICE", subject=subject, body=body,
            withdrawal_id=w.id,
        )
        # The one-time notice flag on the refund is the authoritative "already sent".
        t["already_notified"] = w.oversubscription_notice_sent_at is not None
        out.append(t)
    return out


# ------------------------------------------------------------ existing emails
def _row_key(email_type, investor_id, batch_id, amount):
    amt = round(float(amount), 2) if email_type.startswith("WITHDRAWAL_") and amount is not None else None
    return (email_type, investor_id, batch_id, amt)


def annotate(targets: List[Dict[str, Any]], kind: str) -> None:
    """Adds t['state'] (none|pending|suppressed|failed|queued|sending|sent|no_email) and t['existing_id']."""
    investor_ids = {t["investor_id"] for t in targets if t["investor_id"]}
    rows_by_key: Dict[tuple, List[PendingEmail]] = {}
    if investor_ids:
        rows = (
            db.session.query(PendingEmail)
            .filter(PendingEmail.email_type.in_(KINDS[kind]["types"]), PendingEmail.investor_id.in_(investor_ids))
            .order_by(PendingEmail.id)
            .all()
        )
        for r in rows:
            rows_by_key.setdefault(_row_key(r.email_type, r.investor_id, r.batch_id, r.amount), []).append(r)

    for t in targets:
        t["existing_id"] = None
        if not t["email"]:
            t["state"] = "no_email"
            continue
        if t.get("already_notified"):
            t["state"] = "sent"
            continue
        rows = rows_by_key.get(_row_key(t["email_type"], t["investor_id"], t["batch_id"], t["amount"]), [])
        if not rows:
            t["state"] = "none"
            continue
        active = next((r for r in reversed(rows) if r.status in ACTIVE), None)
        chosen = active or rows[-1]
        t["existing_id"] = chosen.id
        t["state"] = {
            "Pending_Confirmation": "pending", "Suppressed": "suppressed", "Failed": "failed",
            "Queued": "queued", "Sending": "sending", "Confirmed": "sent",
        }.get(chosen.status, "none")


def _will_send(t: Dict[str, Any], include_sent: bool) -> bool:
    if t["state"] in ("none", "pending", "suppressed", "failed"):
        return True
    return t["state"] == "sent" and include_sent


def summarize(targets: List[Dict[str, Any]], include_sent: bool = False) -> Dict[str, int]:
    c = {"total": len(targets), "no_email": 0, "ready": 0, "in_progress": 0, "already_sent": 0, "will_send": 0}
    for t in targets:
        s = t["state"]
        if s == "no_email":
            c["no_email"] += 1
        elif s in ("queued", "sending"):
            c["in_progress"] += 1
        elif s == "sent":
            c["already_sent"] += 1
        else:
            c["ready"] += 1
        if _will_send(t, include_sent):
            c["will_send"] += 1
    return c


def preview(kind: str, fund_id: Optional[int], batch_id: Optional[int], include_sent: bool = False, client_code: Optional[str] = None) -> Dict[str, Any]:
    targets = collect_targets(kind, fund_id, batch_id, client_code)
    if len(targets) > MAX_TARGETS:
        raise BulkEmailError(f"More than {MAX_TARGETS} matches - narrow it to one batch")
    annotate(targets, kind)
    return {
        "kind": kind,
        "label": KINDS[kind]["label"],
        "counts": summarize(targets, include_sent),
        "rows": [
            {k: t.get(k) for k in ("client_code", "name", "email", "fund_name", "batch_name", "amount", "currency", "email_type", "state")}
            for t in targets
        ],
    }


# ---------------------------------------------------------------------- queue
def queue(kind: str, fund_id: Optional[int], batch_id: Optional[int], include_sent: bool, expected_count: Optional[int], client_code: Optional[str] = None) -> Dict[str, Any]:
    """Marks exactly the previewed emails 'Queued'. Returns their ids so the UI can track them."""
    targets = collect_targets(kind, fund_id, batch_id, client_code)
    if len(targets) > MAX_TARGETS:
        raise BulkEmailError(f"More than {MAX_TARGETS} matches - narrow it to one batch")
    annotate(targets, kind)
    chosen = [t for t in targets if _will_send(t, include_sent)]

    if expected_count is None:
        raise BulkEmailError("expected_count (the number shown in the preview) is required")
    if int(expected_count) != len(chosen):
        raise BulkEmailError(
            f"The list changed since you previewed it (now {len(chosen)}, you confirmed {int(expected_count)}). "
            "Nothing was queued - preview again.",
            409,
        )
    if not chosen:
        return {"email_ids": [], "created": 0, "requeued": 0, "skipped": summarize(targets, include_sent)}

    now = datetime.now(timezone.utc)
    ids: List[int] = []
    created = requeued = 0
    try:
        reusable_states = ("pending", "suppressed", "failed")  # annotate() states for REQUEUEABLE statuses
        reuse_ids = [t["existing_id"] for t in chosen if t["state"] in reusable_states and t["existing_id"]]
        reuse = {r.id: r for r in db.session.query(PendingEmail).filter(PendingEmail.id.in_(reuse_ids)).all()} if reuse_ids else {}
        new_rows = []
        for t in chosen:
            row = reuse.get(t["existing_id"]) if t["state"] in reusable_states else None
            if row is not None and row.status in REQUEUEABLE:
                row.status, row.queued_at = "Queued", now
                ids.append(row.id)
                requeued += 1
                continue
            row = PendingEmail(
                batch_id=t["batch_id"], investor_id=t["investor_id"], email_type=t["email_type"],
                status="Queued", subject=t["subject"][:255], body=t["body"],
                recipient_email=t["email"], recipient_name=t["name"], amount=t["amount"],
                fund_name=(t["fund_name"] or None) and str(t["fund_name"])[:100],
                batch_name=(t["batch_name"] or None) and str(t["batch_name"])[:100],
                currency_type=t["currency"] or "USD", queued_at=now, trigger_source="emails.bulk_send",
                withdrawal_id=t.get("withdrawal_id"),
            )
            new_rows.append(row)
        db.session.add_all(new_rows)
        db.session.flush()
        ids.extend(r.id for r in new_rows)
        created = len(new_rows)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info(f"Bulk send '{kind}' fund={fund_id} batch={batch_id}: {created} created, {requeued} requeued")
    return {"email_ids": ids, "created": created, "requeued": requeued, "skipped": summarize(targets, include_sent)}


# --------------------------------------------------------------- sample/preview
def sample(kind: str, fund_id: Optional[int], batch_id: Optional[int], client_code: str) -> Dict[str, Any]:
    """The exact email (subject, text, branded HTML) and attachment name for ONE investor. Sends nothing."""
    from app.utils.email_template import render_branded_email_html, get_email_title

    targets = collect_targets(kind, fund_id, batch_id, client_code)
    if not targets:
        raise BulkEmailError("That investor is not in this selection", 404)
    t = targets[0]
    pdf = _pdf_spec(t)
    return {
        "to": t["email"], "name": t["name"], "subject": t["subject"], "body": t["body"],
        "html": _inline_logo(render_branded_email_html(get_email_title(t["email_type"]), t["body"])),
        "attachment_name": pdf["name"] if pdf else None,
    }


def _inline_logo(html: str) -> str:
    """
    Preview only: a sent email carries the logo as an embedded attachment
    (cid:), which a browser preview can't resolve — so it showed as a broken
    image. Swap in the same image as a data URI for the preview.
    """
    try:
        import base64
        from app.utils.email_template import LOGO_CONTENT_ID, get_axys_logo_bytes
        logo = get_axys_logo_bytes()
        if not logo:
            return html
        data = base64.b64encode(logo).decode("ascii")
        return html.replace(f"cid:{LOGO_CONTENT_ID}", f"data:image/png;base64,{data}")
    except Exception:
        return html


def _pdf_spec(t: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Which PDF is attached for this target (mirrors _send_pending_email_now). None = no attachment."""
    et, code = t["email_type"], t["client_code"]
    if et == "DEPOSIT_CONFIRMATION" and t.get("batch_id"):
        return {"name": f"deposit-confirmation-{code}-{t['batch_id']}.pdf", "kind": "deposit"}
    if et == "OFFSHORE_TRANSFER" and t.get("batch_id"):
        return {"name": f"transfer-confirmation-{code}-{t['batch_id']}.pdf", "kind": "transfer"}
    if et == "INVESTMENT_ACTIVE" and t.get("batch_id"):
        return {"name": f"deployment-confirmation-{code}-{t['batch_id']}.pdf", "kind": "deployment"}
    if et == "OVERSUBSCRIPTION_REFUND_NOTICE":
        return {"name": f"oversubscription-notice-{code}.pdf", "kind": "oversubscription"}
    if et in ("WITHDRAWAL_RECEIVED", "WITHDRAWAL_APPROVED") and t.get("withdrawal_id"):
        return {"name": f"withdrawal-statement-{code}-{t['withdrawal_id']}.pdf", "kind": "withdrawal"}
    return None


def sample_pdf(kind: str, fund_id: Optional[int], batch_id: Optional[int], client_code: str):
    """(BytesIO, filename) of the attachment this investor's email would carry, or raises BulkEmailError."""
    from app.Investments import route as r

    targets = collect_targets(kind, fund_id, batch_id, client_code)
    if not targets:
        raise BulkEmailError("That investor is not in this selection", 404)
    t = targets[0]
    spec = _pdf_spec(t)
    if not spec:
        raise BulkEmailError("This email type has no attachment", 404)
    code = t["client_code"]
    if spec["kind"] == "deposit":
        buf = r._generate_deposit_receipt_pdf_bytes(code, int(t["batch_id"]))
    elif spec["kind"] == "transfer":
        buf = r._generate_transfer_receipt_pdf_bytes(code, int(t["batch_id"]))
    elif spec["kind"] == "deployment":
        buf = r._generate_deployment_receipt_pdf_bytes(code, int(t["batch_id"]))
    elif spec["kind"] == "withdrawal":
        buf = r._generate_withdrawal_statement_pdf_bytes(code, int(t["withdrawal_id"]))
    else:
        inv = db.session.get(Investment, t["investor_id"])
        buf = r._generate_oversubscription_notice_pdf_bytes(code, int(inv.fund_id))
    if isinstance(buf, tuple) or buf is None:
        raise BulkEmailError("Could not generate the statement PDF", 500)
    buf.seek(0)
    return buf, spec["name"]


def status_counts(ids: List[int]) -> Dict[str, int]:
    if not ids:
        return {}
    rows = (
        db.session.query(PendingEmail.status, func.count(PendingEmail.id))
        .filter(PendingEmail.id.in_(ids))
        .group_by(PendingEmail.status)
        .all()
    )
    return {s: c for s, c in rows}
