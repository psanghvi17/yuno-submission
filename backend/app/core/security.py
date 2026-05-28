import hashlib
import secrets

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_password_reset_token() -> tuple[str, str]:
    """Return (plain_token, sha256_hex_hash) for storage."""
    plain = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plain.encode()).hexdigest()
    return plain, token_hash


def hash_password_reset_token(plain_token: str) -> str:
    return hashlib.sha256(plain_token.encode()).hexdigest()
