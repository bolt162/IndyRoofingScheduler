import os

OFFICE_PHONE = "(317) 886-7436"
OFFICE_ADDRESS = "5240 Elmwood Ave, Suite 200, Indianapolis, IN 46203"
COMPANY_NAME = "Indy Roof and Restoration"

VALID_MODES = {"off", "test", "live"}


def email_mode() -> str:
    """off (default) sends nothing; test sends everything to EMAIL_TEST_RECIPIENT; live sends to customers."""
    mode = os.getenv("EMAIL_MODE", "off").strip().lower()
    return mode if mode in VALID_MODES else "off"


def smtp_settings() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "from_name": os.getenv("SMTP_FROM_NAME", f"{COMPANY_NAME} (No Reply)"),
    }


def test_recipient() -> str:
    return os.getenv("EMAIL_TEST_RECIPIENT", "").strip()


def office_alert_recipient() -> str:
    """Where office flags (unknown shingle product, etc.) go. Blank = log only."""
    return os.getenv("EMAIL_OFFICE_ALERTS", "").strip()
