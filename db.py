import argparse
import os
from getpass import getpass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def connect():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL to the shared PostgreSQL database.")
    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    admin = commands.add_parser("create-admin")
    admin.add_argument("username")
    args = parser.parse_args()

    if args.command == "init":
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with connect() as db:
            db.execute(schema)
        return

    from pydantic import ValidationError

    from auth import Registration, passwords

    password = getpass("Admin password: ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match.")
    try:
        account = Registration(username=args.username, password=password)
    except ValidationError:
        parser.error("Use a 3–50 character username and a 12–128 character password.")

    with connect() as db:
        row = db.execute(
            """
            INSERT INTO users (username, password_hash, role, status)
            VALUES (%s, %s, 'admin', 'approved')
            ON CONFLICT (username) DO NOTHING RETURNING id
            """,
            (account.username, passwords.hash(account.password.get_secret_value())),
        ).fetchone()
    if row is None:
        parser.error("Username is already in use.")
    print(f"Created administrator {account.username}.")


if __name__ == "__main__":
    main()
