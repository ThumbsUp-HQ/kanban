# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Local Admin authentication with Argon2id and HMAC-SHA256 pepper (KB-P2-04)."""

from kanban.auth.local.hashing import (
    DUMMY_HASH,
    get_argon2_semaphore,
    get_auth_pepper,
    hash_password,
    hash_password_sync,
    needs_rehash,
    reset_argon2_semaphore,
    verify,
    verify_password,
    verify_password_sync,
)
from kanban.auth.local.service import LocalAdminLoginService

__all__ = [
    "DUMMY_HASH",
    "LocalAdminLoginService",
    "get_argon2_semaphore",
    "get_auth_pepper",
    "hash_password",
    "hash_password_sync",
    "needs_rehash",
    "reset_argon2_semaphore",
    "verify",
    "verify_password",
    "verify_password_sync",
]
