#!/usr/bin/env python3
"""Write a production .env for the CI deployment jobs (and local rehearsals).

    python3 scripts/ci-generate-env.py AGE_IDENTITY_FILE [.env]

Starts from .env.example, fills every required secret with random values,
enables the production and monitoring profiles, uses DOMAIN=localhost and
the public key of AGE_IDENTITY_FILE (created with age-keygen) as the backup
recipient. Extra KEY=VALUE pairs can be passed in CI_ENV_OVERRIDES
(newline-separated). Never use the result for a real installation.
"""

import base64
import os
import re
import secrets
import sys


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    identity = open(argv[1]).read()
    match = re.search(r"public key: (\S+)", identity)
    if not match:
        print(f"{argv[1]}: no 'public key:' line (age-keygen output expected)", file=sys.stderr)
        return 2
    target = argv[2] if len(argv) == 3 else ".env"
    env = open(".env.example").read()
    values = {
        "COMPOSE_PROFILES": "production,monitoring",
        "APP_BASE_URL": "https://localhost",
        "ALLOWED_ORIGINS": "https://localhost",
        "DOMAIN": "localhost",
        "APP_SECRET_KEY": secrets.token_urlsafe(48),
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "PRINTER_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "AGE_RECIPIENT": match.group(1),
    }
    for line in os.environ.get("CI_ENV_OVERRIDES", "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    for key, value in values.items():
        env, count = re.subn(rf"^{key}=.*$", f"{key}={value}", env, flags=re.M)
        if not count:
            env += f"\n{key}={value}\n"
    with open(target, "w") as handle:
        handle.write(env)
    os.chmod(target, 0o600)
    print(f"{target} written (DOMAIN=localhost, profiles production,monitoring)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
