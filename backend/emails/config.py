import os

OFFICE_PHONE = "(317) 886-7436"
OFFICE_ADDRESS = "5240 Elmwood Ave, Suite 200, Indianapolis, IN 46203"
COMPANY_NAME = "Indy Roof and Restoration"

VALID_MODES = {"off", "test", "live"}


def _clean_env(value: str) -> str:
    """Tolerate values pasted with quotes or stray spaces, e.g. '"test" '."""
    return value.strip().strip("'\"").strip()


def email_mode_raw() -> str | None:
    """Exactly what the server received, for the status page (not a secret)."""
    return os.getenv("EMAIL_MODE")


def email_mode() -> str:
    """off (default) sends nothing; test sends everything to EMAIL_TEST_RECIPIENT; live sends to customers."""
    mode = _clean_env(os.getenv("EMAIL_MODE", "off")).lower()
    return mode if mode in VALID_MODES else "off"


def smtp_settings() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "user": _clean_env(os.getenv("SMTP_USER", "")),
        "password": _clean_env(os.getenv("SMTP_PASS", "")).replace(" ", ""),
        "from_name": os.getenv("SMTP_FROM_NAME", f"{COMPANY_NAME} (No Reply)"),
    }


def test_recipient() -> str:
    return _clean_env(os.getenv("EMAIL_TEST_RECIPIENT", ""))


def office_alert_recipient() -> str:
    """Where office flags (unknown shingle product, etc.) go. Blank = log only."""
    return os.getenv("EMAIL_OFFICE_ALERTS", "").strip()
