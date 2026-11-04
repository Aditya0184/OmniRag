"""Set or reset the single local owner's password without putting it in command arguments."""

import argparse
import getpass
import os
import secrets

from omnirag.auth import AuthStore
from omnirag.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="Replace owner password and revoke sessions"
    )
    parser.add_argument(
        "--generate", action="store_true", help="Save a generated password to a private local file"
    )
    args = parser.parse_args()
    store = AuthStore(Settings().data_dir.resolve() / "auth")
    store.initialize()
    if store.configured() and not args.reset:
        parser.error(
            "Owner already configured. Use --reset only when you intend to revoke all sessions."
        )
    target = store.directory / "owner-password.txt"
    if args.generate:
        password = secrets.token_urlsafe(24)
        # Exclusive creation prevents overwriting a previous credential handoff.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(
                "OmniRAG local owner password\n\n"
                + password
                + "\n\nSign in at http://127.0.0.1:8000 and use Change password.\n"
            )
    else:
        password = getpass.getpass("New owner password (15-128 characters): ")
        if password != getpass.getpass("Repeat password: "):
            parser.error("Passwords did not match.")
    try:
        store.set_password(password, replace=args.reset)
    except ValueError as exc:
        parser.error(str(exc))
    print("Owner configured; all previous sessions revoked.")
    if args.generate:
        print(f"Password saved privately to {target}. It was not printed or logged.")


if __name__ == "__main__":
    main()
