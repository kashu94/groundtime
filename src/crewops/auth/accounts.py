"""Password resets from inside the app, by admins.

An admin resets anyone's password except another admin's and their own: those go through
the team command (``python -m crewops.auth.provision --apply --reset-passwords``), run by
whoever holds the AWS account.

The new password is generated here, never typed by the admin, and set as permanent, so it
works at once; the admin passes it on to the person by hand. Each reset is logged on the
server with who did it.
"""

from __future__ import annotations

import secrets
import string
from collections.abc import Iterable
from typing import Any

from crewops.auth.provision import password_problems
from crewops.domain import Role


class AccountError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def may_reset(
    caller_user: str, caller_roles: Iterable[Role], target_user: str, target_roles: Iterable[Role]
) -> None:
    """Raise AccountError unless this caller may reset this account's password."""
    mine, theirs = frozenset(caller_roles), frozenset(target_roles)
    if Role.ADMIN not in mine:
        raise AccountError("FORBIDDEN", "only an admin resets passwords")
    if target_user == caller_user:
        raise AccountError("FORBIDDEN", "you can't reset your own password here")
    if Role.ADMIN in theirs:
        raise AccountError("FORBIDDEN", "an admin's password is reset with the team command")


def new_password(length: int = 16) -> str:
    """Random, and always within the pool's policy (upper, lower, digit, symbol)."""
    symbols = "!#%+-=?@^_"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if not password_problems(password) and any(c in symbols for c in password):
            return password


class Accounts:
    """The user pool's password call, kept apart so tests need no Cognito."""

    def __init__(self, cognito: Any, pool_id: str) -> None:
        self.cognito = cognito
        self.pool_id = pool_id

    def set_password(self, username: str, password: str) -> None:
        try:
            self.cognito.admin_set_user_password(
                UserPoolId=self.pool_id, Username=username, Password=password, Permanent=True
            )
        except self.cognito.exceptions.UserNotFoundException:
            raise AccountError("NOT_FOUND", f"no account {username}") from None
