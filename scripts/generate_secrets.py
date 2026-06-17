#!/usr/bin/env python3
"""Generate strong secrets for a deployment's .env.

Prints a fresh JWT_SECRET_KEY and a base64-encoded 32-byte MASTER_KEK. These are the two
secrets the app refuses to start without outside development. Pipe into your secret
manager — do NOT commit the output.

    python scripts/generate_secrets.py
"""

from __future__ import annotations

import base64
import secrets


def main() -> None:
    jwt_secret = secrets.token_urlsafe(64)
    master_kek = base64.b64encode(secrets.token_bytes(32)).decode()
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"MASTER_KEK={master_kek}")


if __name__ == "__main__":
    main()
