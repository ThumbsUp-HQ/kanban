"""Operations module: backup, restore, standalone-to-production promotion."""

from __future__ import annotations

from kanban.ops.backup_crypto import (
    CHUNK_SIZE,
    KDF_MODE_ARGON2ID,
    KDF_MODE_RAW,
    BackupCryptoError,
    BackupIntegrityError,
    KeySource,
    PassphraseKeySource,
    RawKeySource,
    decode_raw_key,
    decrypt_stream,
    derive_key_argon2id,
    encrypt_stream,
)
from kanban.ops.backup_service import (
    BackupError,
    BackupManifest,
    BackupSummary,
    RestoreError,
    RestoreReport,
    RestoreVerificationError,
    TargetDatabaseNotEmptyError,
    create_backup,
    resolve_pg_dump_bin,
    resolve_pg_restore_bin,
    restore_backup,
    verify_backup,
)
from kanban.ops.compose_export import (
    ComposeExportSummary,
    export_production_bundle,
)

__all__ = [
    "CHUNK_SIZE",
    "KDF_MODE_ARGON2ID",
    "KDF_MODE_RAW",
    "BackupCryptoError",
    "BackupError",
    "BackupIntegrityError",
    "BackupManifest",
    "BackupSummary",
    "ComposeExportSummary",
    "KeySource",
    "PassphraseKeySource",
    "RawKeySource",
    "RestoreError",
    "RestoreReport",
    "RestoreVerificationError",
    "TargetDatabaseNotEmptyError",
    "create_backup",
    "decode_raw_key",
    "decrypt_stream",
    "derive_key_argon2id",
    "encrypt_stream",
    "export_production_bundle",
    "resolve_pg_dump_bin",
    "resolve_pg_restore_bin",
    "restore_backup",
    "verify_backup",
]
