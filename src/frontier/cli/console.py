"""`make console` and `make ancients` — run the operator console, or make its first operator.

The first operator cannot be created from inside the console: something has to let the first
person in, and that is this command, run by whoever has the deployment (ADMIN §2, QA-1).
"""

from __future__ import annotations

import asyncio
import secrets
import sys

from frontier.adapters.console.app import bootstrap, worlds_of
from frontier.config.settings import Settings

ORIGIN_NAME = "The Great Ancients"


def main() -> None:
    settings = Settings()
    email = sys.argv[1] if len(sys.argv) > 1 else "ancients@frontier.local"
    password = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(18)

    operator_id = asyncio.run(bootstrap(settings, email, password, ORIGIN_NAME))
    print(f"{ORIGIN_NAME} — the operator every other one descends from")
    print(f"  id       {operator_id}")
    print(f"  email    {email}")
    print(f"  password {password}")
    print(f"  worlds   {', '.join(worlds_of(settings))}")
    print("\nNobody can revoke this account, and nothing else can create one.")


if __name__ == "__main__":
    main()
