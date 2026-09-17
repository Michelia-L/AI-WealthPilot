"""Provision a local identity: python -m api.create_user.

Credentials are entered interactively, never accepted as command-line flags.
No public registration endpoint or default password is installed.
"""

import argparse
import getpass
import sys
import warnings

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from api import db
from api.auth import create_user
from api.schemas import LoginRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-admin",
        action="store_true",
        help="Grant admin membership in the local workspace",
    )
    options = parser.parse_args(argv or [])
    try:
        email = input("Email: ")
        # Fail if this terminal cannot hide password entry (no echo fallback).
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Password (15–1024 characters): ")
            confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 1
        credentials = LoginRequest(email=email, password=password)
        db.init_db()
        with Session(db.engine) as session:
            user = create_user(session, credentials)
            if options.local_admin:
                from api.ownership import ensure_local_organization, set_membership

                org = ensure_local_organization(session)
                set_membership(session, org.id, user.id, "admin")
                session.commit()
    except ValidationError:
        print("Enter a valid email and password.", file=sys.stderr)
        return 1
    except ValueError as exc:
        # create_user's controlled errors contain no supplied credentials.
        print(str(exc), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("User creation cancelled; use an interactive terminal.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        # SQL exceptions can contain bound identity/hash values; do not print them.
        print("Cannot create user in the configured database.", file=sys.stderr)
        return 1
    print("User created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
