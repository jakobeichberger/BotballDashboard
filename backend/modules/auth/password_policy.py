"""Password policy shared by account creation, password change and reset."""

MIN_LENGTH = 10


def password_problem(password: str, email: str | None = None) -> str | None:
    """Return why ``password`` is not acceptable, or None when it is."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters"
    if len(set(password)) == 1:
        return "Password must not consist of a single repeated character"
    if email and password.strip().lower() == email.strip().lower():
        return "Password must not be the e-mail address"
    return None


def check_password(password: str, email: str | None = None) -> str:
    """Pydantic-validator friendly: raise ValueError, return the password otherwise."""
    problem = password_problem(password, email)
    if problem:
        raise ValueError(problem)
    return password
