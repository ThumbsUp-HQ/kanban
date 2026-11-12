"""Local filesystem blob store with content-addressed SHA-256 storage (S5.4)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

STORAGE_KEY_REGEX = re.compile(r"^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")


class BlobStorageError(ValueError):
    """Raised when blob storage operations fail or paths are invalid."""


class LocalFilesystemBlobStore:
    """Content-addressed filesystem blob store for immutable attachment blobs."""

    def __init__(self, root_dir: Path | str) -> None:
        """Initialize blob store rooted at ``root_dir``."""
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def store(self, data: bytes) -> tuple[str, bytes]:
        """Store sanitized blob bytes atomically using O_CREAT | O_EXCL | O_NOFOLLOW.

        Returns:
            Tuple of (storage_key, raw_sha256_bytes).

        """
        raw_sha = hashlib.sha256(data).digest()
        h = hashlib.sha256(data).hexdigest()
        storage_key = f"sha256/{h[:2]}/{h[2:4]}/{h}"

        target_dir = self.root_dir / "sha256" / h[:2] / h[2:4]
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / h

        # Atomic write with mode 0600 and O_NOFOLLOW
        if not target_path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(str(target_path), flags, 0o600)
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
            except FileExistsError:
                # Already written concurrently
                pass

        return storage_key, raw_sha

    def get_path(self, storage_key: str) -> Path:
        """Resolve storage key to an absolute filesystem Path ensuring no directory traversal."""
        if not STORAGE_KEY_REGEX.match(storage_key):
            msg = f"Invalid storage key format: {storage_key!r}"
            raise BlobStorageError(msg)

        resolved = (self.root_dir / storage_key).resolve()
        if not str(resolved).startswith(str(self.root_dir)):
            msg = f"Storage key traverses outside root directory: {storage_key!r}"
            raise BlobStorageError(msg)

        return resolved

    def read(self, storage_key: str) -> bytes:
        """Read blob content from disk for a valid storage key."""
        path = self.get_path(storage_key)
        if not path.is_file():
            msg = f"Blob not found for storage key: {storage_key}"
            raise BlobStorageError(msg)
        return path.read_bytes()

    def exists(self, storage_key: str) -> bool:
        """Check whether blob exists for storage key."""
        try:
            return self.get_path(storage_key).is_file()
        except BlobStorageError:
            return False
