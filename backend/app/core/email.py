import re

# Looser than Pydantic EmailStr so dev seeds like admin@example.com and DB lookups work.
_LOGIN_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_valid_login_email(value: str) -> bool:
    return bool(_LOGIN_EMAIL_RE.match(normalize_email(value)))
