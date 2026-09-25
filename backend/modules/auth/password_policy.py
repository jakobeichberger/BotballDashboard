"""Password policy shared by account creation, password change and reset."""

from functools import cache
from pathlib import Path

MIN_LENGTH = 10
# bcrypt only uses the first 72 bytes of a password; bcrypt 5 refuses longer
# ones instead of cutting them off. Bytes, not characters: in UTF-8 an umlaut
# counts twice and an emoji four times.
MAX_BYTES = 72
COMMON_PASSWORDS_FILE = Path(__file__).with_name("common_passwords.txt")


@cache
def common_passwords() -> frozenset[str]:
    """The bundled list of leaked/common passwords, lowercased (see the file header)."""
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line and not line.startswith("#"))


def is_common_password(password: str) -> bool:
    return password.strip().lower() in common_passwords()


def password_too_long(password: str) -> bool:
    """More than bcrypt can hash (MAX_BYTES of UTF-8)."""
    return len(password.encode("utf-8")) > MAX_BYTES


def password_problem(password: str, email: str | None = None) -> str | None:
    """Return why ``password`` is not acceptable, or None when it is."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters"
    if password_too_long(password):
        return f"Password must be at most {MAX_BYTES} bytes (umlauts count 2, emoji 4)"
    if len(set(password)) == 1:
        return "Password must not consist of a single repeated character"
    if email and password.strip().lower() == email.strip().lower():
        return "Password must not be the e-mail address"
    if is_common_password(password):
        return "Password is on a list of common or leaked passwords"
    return None


def check_password(password: str, email: str | None = None) -> str:
    """Pydantic-validator friendly: raise ValueError, return the password otherwise."""
    problem = password_problem(password, email)
    if problem:
        raise ValueError(problem)
    return password
