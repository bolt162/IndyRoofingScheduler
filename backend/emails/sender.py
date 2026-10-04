"""
SMTP sending with the EMAIL_MODE safety switch. Every attempt is logged to email_logs.

  off  -> nothing sends (logged as skipped)
  test -> everything goes to EMAIL_TEST_RECIPIENT, subject prefixed "[TEST: Customer Name]"
  live -> real recipients
"""
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy.orm import Session

from backend.emails.compose import ComposedEmail
from backend.emails.config import email_mode, smtp_settings, test_recipient
from backend.models.email import EmailLog

logger = logging.getLogger("emails")


def _log(db: Session | None, job_id, email: ComposedEmail, recipient: str, mode: str,
         result: str, detail: str = "") -> None:
    if db is None:
        return
    db.add(EmailLog(job_id=job_id, template=email.template, recipient=recipient,
                    subject=email.subject, mode=mode, result=result, detail=detail or None))
    db.commit()


def send(db: Session | None, job_id: int | None, email: ComposedEmail, to: list[str],
         customer_name: str = "", mode: str | None = None) -> bool:
    """Send one email. Returns True only if it was actually handed to the SMTP server."""
    mode = mode or email_mode()
    to = [addr for addr in to if addr]
    real_to = ", ".join(to)

    if mode == "off":
        _log(db, job_id, email, real_to, mode, "skipped", "EMAIL_MODE=off")
        return False
    if not to:
        _log(db, job_id, email, "", mode, "skipped", "no recipient")
        return False

    subject = email.subject
    recipients = to
    if mode == "test":
        tr = test_recipient()
        if not tr:
            _log(db, job_id, email, real_to, mode, "failed", "EMAIL_TEST_RECIPIENT not set")
            return False
        subject = f"[TEST: {customer_name or 'unknown'}] {subject}"
        recipients = [tr]

    cfg = smtp_settings()
    if not cfg["user"] or not cfg["password"]:
        _log(db, job_id, email, real_to, mode, "failed", "SMTP_USER/SMTP_PASS not set")
        return False

    msg = EmailMessage()
    msg["From"] = formataddr((cfg["from_name"], cfg["user"]))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=cfg["user"].split("@")[-1] or None)
    msg.set_content(email.text)
    msg.add_alternative(email.html, subtype="html")

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
    except Exception as e:
        logger.error(f"Email send failed (job {job_id}, {email.template}): {e}")
        _log(db, job_id, email, ", ".join(recipients), mode, "failed", str(e)[:1000])
        return False

    detail = f"intended for {real_to}" if mode == "test" else ""
    _log(db, job_id, email, ", ".join(recipients), mode, "sent", detail)
    return True
