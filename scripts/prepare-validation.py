"""Generate a private pilot environment file without printing secrets or overwriting files."""

import argparse
import json
import os
import re
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def prepare(domain, review, destination):
    if not re.fullmatch(
        r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,63}",
        domain,
    ):
        raise ValueError("Use a DNS hostname only, without a scheme, path or port.")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9 _./:#-]{7,159}", review.strip()
    ) or review.lower().startswith(("placeholder", "replace-")):
        raise ValueError(
            "Enter the operator deployment review reference (at least 8 characters)."
        )
    values = {
        "APP_ENV": "validation",
        "VALIDATION_DOMAIN": domain,
        "PUBLIC_API_URL": f"https://{domain}/api",
        "ALLOWED_ORIGINS": json.dumps([f"https://{domain}"]),
        "SECURE_COOKIES": "true",
        "PUBLIC_INDEXING_ENABLED": "false",
        "ALLOW_UNVERIFIED_MODELS": "false",
        "PROVIDER_MODE": "sandbox",
        "WORKER_ENABLED": "false",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "VALIDATION_ACCESS_CODE": secrets.token_urlsafe(36),
        "VALIDATION_REVIEW_REF": review.strip(),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(36),
        "APP_DATABASE_PASSWORD": secrets.token_urlsafe(36),
        "WORKER_DATABASE_PASSWORD": secrets.token_urlsafe(36),
        "MODEL_MAX_COST_MICROS": "20000",
        "MODEL_CACHE_SECONDS": "21600",
        "PAYMENT_WEBHOOK_SECRET": secrets.token_urlsafe(36),
    }
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
        target.write(
            "# PRIVATE: preserve this file securely; never commit or share it publicly.\n"
        )
        for key, value in values.items():
            # Quote review metadata so dotenv cannot interpret comments or interpolate variables.
            target.write(f"{key}='{value}'\n")
    try:
        destination.chmod(0o600)
    except OSError:
        pass  # Windows operators must restrict the file's NTFS access separately.
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env.validation",
    )
    args = parser.parse_args()
    try:
        path = prepare(args.domain.lower(), args.review, args.destination.resolve())
    except (ValueError, FileExistsError) as error:
        raise SystemExit(str(error)) from None
    print(f"Private pilot configuration created: {path}")
    print(
        "No provider account is enabled. Keep the signup code and encryption key private."
    )
