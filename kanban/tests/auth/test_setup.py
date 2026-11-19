# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, SLF001, ARG001, TRY003, EM101
"""Unit tests for setup bootstrap service, claim handling, and RLS binding (KAN-7)."""

from __future__ import annotations

import io
import os
import stat
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException
from kanban.auth.setup import (
    SETUP_TOKEN_REGEX,
    SetupBootstrapService,
    generate_setup_token,
    hash_setup_token,
    mint_setup_token_if_uninitialized,
)
from kanban.security.keys import KeyMaterial


def test_generate_and_hash_setup_token() -> None:
    """Verify setup token generator format and HMAC derivation."""
    token = generate_setup_token()
    assert SETUP_TOKEN_REGEX.match(token)

    pepper = b"test-pepper-32-bytes-long-key!!"
    digest1 = hash_setup_token(token, pepper)
    digest2 = hash_setup_token(token, pepper)
    assert digest1 == digest2
    assert len(digest1) == 32


def test_persist_token_direct_success(tmp_path: Path) -> None:
    """_persist_token writes token to destination with 0o600 permissions."""
    dest = tmp_path / "setup_token"
    token = generate_setup_token()

    written = SetupBootstrapService._persist_token(str(dest), token)
    assert written == str(dest)
    assert dest.read_text(encoding="utf-8") == token
    mode = stat.S_IMODE(dest.stat().st_mode)
    assert mode == 0o600


def test_persist_token_permission_error_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When primary destination raises PermissionError, fall back to writable data dir."""
    fallback_dir = tmp_path / "fallback_data"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KB_DATA_DIR", str(fallback_dir))

    token = generate_setup_token()
    unwritable_dest = "/run/kanban/setup_token"

    real_mkdir = Path.mkdir

    def guarded_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,  # noqa: FBT001, FBT002
        exist_ok: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        if "/run/kanban" in str(self):
            msg = "Permission denied: /run/kanban"
            raise PermissionError(msg)
        real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)

    written = SetupBootstrapService._persist_token(unwritable_dest, token)
    assert written is not None
    assert str(fallback_dir) in written
    fallback_file = Path(written)
    assert fallback_file.is_file()
    assert fallback_file.read_text(encoding="utf-8") == token


def test_persist_token_kb_run_dir_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When primary destination raises PermissionError, falls back to KB_RUN_DIR."""
    run_dir = tmp_path / "custom_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KB_RUN_DIR", str(run_dir))
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    token = generate_setup_token()
    real_mkdir = Path.mkdir

    def guarded_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,  # noqa: FBT001, FBT002
        exist_ok: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        if "primary_run" in str(self):
            msg = "Primary run unwritable"
            raise PermissionError(msg)
        real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)

    written = SetupBootstrapService._persist_token(str(tmp_path / "primary_run" / "tok"), token)
    assert written is not None
    assert str(run_dir) in written


def test_persist_token_permission_error_and_all_fallbacks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When primary raises PermissionError and all fallbacks fail, returns None."""
    token = generate_setup_token()

    def always_fail(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("All unwritable")

    monkeypatch.setattr(Path, "mkdir", always_fail)

    written = SetupBootstrapService._persist_token("/var/lib/kanban/data/setup_token", token)
    assert written is None


def test_persist_token_all_fail_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all candidate destinations raise OSError, returns None."""
    token = generate_setup_token()

    def failing_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("Disk failure")

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    written = SetupBootstrapService._persist_token(str(tmp_path / "token"), token)
    assert written is None


def test_persist_token_primary_oserror_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-PermissionError OSError on primary destination returns None without fallback."""
    token = generate_setup_token()

    def generic_oserror(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("Read-only file system")

    monkeypatch.setattr(Path, "mkdir", generic_oserror)

    written = SetupBootstrapService._persist_token(str(tmp_path / "token"), token)
    assert written is None


@pytest.mark.asyncio
async def test_claim_initial_admin_binds_rls_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """claim_initial_admin binds RLS context for admin principal and workspace before inserts."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    service = SetupBootstrapService(mock_factory, key_material=key_material)

    admin_principal_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    local_card_id = uuid.uuid4()

    mock_session = AsyncMock(spec=AsyncSession)

    # Return values for session.execute:
    # 1. setup_consume_and_create_admin returning mapping
    consume_res = MagicMock()
    consume_res.mappings.return_value.first.return_value = {
        "principal_id": admin_principal_id,
        "workspace_id": workspace_id,
        "local_card_id": local_card_id,
    }

    # 2. UPDATE workspaces
    update_res = MagicMock()

    # 3. SELECT id FROM projects (returns None to trigger insert)
    proj_check_res = MagicMock()
    proj_check_res.first.return_value = None

    # 4. SELECT uuidv7()
    proj_uuid = uuid.uuid4()
    proj_res = MagicMock()
    proj_res.scalar_one.return_value = proj_uuid

    # 5. INSERT objects
    obj_res = MagicMock()

    # 6. INSERT projects
    proj_insert_res = MagicMock()

    mock_session.execute.side_effect = [
        consume_res,
        update_res,
        proj_check_res,
        proj_res,
        obj_res,
        proj_insert_res,
    ]

    bound_contexts: list[RLSContext] = []

    async def fake_bind(session: AsyncSession, ctx: RLSContext) -> None:
        bound_contexts.append(ctx)

    monkeypatch.setattr("kanban.auth.setup.bind_rls_context", fake_bind)

    valid_token = generate_setup_token()
    p_id, ws_id, card_id = await service.claim_initial_admin(
        mock_session,
        token=valid_token,
        username="admin",
        display_name="Admin User",
        email="admin@example.com",
        password="ValidPassword123!",
        workspace_name="Custom Workspace",
        workspace_slug="custom-ws",
        project_name="Custom Project",
        project_key="CUST",
    )

    assert p_id == str(admin_principal_id)
    assert ws_id == str(workspace_id)
    assert card_id == str(local_card_id)

    # Verify RLS binding occurred with exact principal_id and workspace_id
    assert len(bound_contexts) == 1
    assert bound_contexts[0].principal_id == admin_principal_id
    assert bound_contexts[0].workspace_id == workspace_id


@pytest.mark.asyncio
async def test_claim_initial_admin_invalid_token_format() -> None:
    """Malformed setup token raises ProblemException with SETUP_TOKEN_INVALID."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    service = SetupBootstrapService(mock_factory, key_material=key_material)
    mock_session = AsyncMock(spec=AsyncSession)

    with pytest.raises(ProblemException) as exc_info:
        await service.claim_initial_admin(
            mock_session,
            token="invalid-format-token",
            username="admin",
            display_name="Admin",
            email="admin@example.com",
            password="password123",
        )

    assert exc_info.value.code == "SETUP_TOKEN_INVALID"
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_claim_initial_admin_consumed_token_returns_none() -> None:
    """When setup_consume_and_create_admin returns no rows, raises SETUP_TOKEN_INVALID."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    service = SetupBootstrapService(mock_factory, key_material=key_material)
    mock_session = AsyncMock(spec=AsyncSession)

    consume_res = MagicMock()
    consume_res.mappings.return_value.first.return_value = None
    mock_session.execute.return_value = consume_res

    valid_token = generate_setup_token()
    with pytest.raises(ProblemException) as exc_info:
        await service.claim_initial_admin(
            mock_session,
            token=valid_token,
            username="admin",
            display_name="Admin",
            email="admin@example.com",
            password="password123",
        )

    assert exc_info.value.code == "SETUP_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_mint_token_if_uninitialized_and_wrapper(tmp_path: Path) -> None:
    """mint_token_if_uninitialized writes banner and persists token to file."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    mock_session = AsyncMock(spec=AsyncSession)

    class FakeSessionContext:
        async def __aenter__(self) -> AsyncSession:
            return mock_session

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_factory.session.return_value = FakeSessionContext()

    res = MagicMock()
    res.scalar_one.return_value = True
    mock_session.execute.return_value = res

    target_token_file = tmp_path / "setup_token"
    with patch.dict(os.environ, {"KB_SETUP_TOKEN_FILE": str(target_token_file)}):
        stdout = io.StringIO()
        token = await mint_setup_token_if_uninitialized(
            mock_factory,
            key_material=key_material,
            stdout=stdout,
        )

    assert token is not None
    assert SETUP_TOKEN_REGEX.match(token)
    output = stdout.getvalue()
    assert "[REDACTED:SETUP_TOKEN]" in output
    assert f"claim token written to {target_token_file}" in output
    assert target_token_file.read_text(encoding="utf-8") == token


@pytest.mark.asyncio
async def test_mint_token_already_initialized_returns_none() -> None:
    """When instance is already initialized, mint_token returns None."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    mock_session = AsyncMock(spec=AsyncSession)

    class FakeSessionContext:
        async def __aenter__(self) -> AsyncSession:
            return mock_session

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_factory.session.return_value = FakeSessionContext()

    res = MagicMock()
    res.scalar_one.return_value = False
    mock_session.execute.return_value = res

    svc = SetupBootstrapService(mock_factory, key_material=key_material)
    token = await svc.mint_token_if_uninitialized()
    assert token is None


@pytest.mark.asyncio
async def test_is_initialized() -> None:
    """is_initialized executes setup_is_initialized() and returns bool."""
    mock_factory = MagicMock(spec=RLSSessionFactory)
    svc = SetupBootstrapService(mock_factory)
    mock_session = AsyncMock(spec=AsyncSession)

    res = MagicMock()
    res.scalar_one.return_value = True
    mock_session.execute.return_value = res

    assert await svc.is_initialized(mock_session) is True


@pytest.mark.asyncio
async def test_claim_initial_admin_existing_project_skips_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When project identifier already exists, skips inserting project row."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_factory = MagicMock(spec=RLSSessionFactory)
    service = SetupBootstrapService(mock_factory, key_material=key_material)

    admin_principal_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    local_card_id = uuid.uuid4()

    mock_session = AsyncMock(spec=AsyncSession)

    consume_res = MagicMock()
    consume_res.mappings.return_value.first.return_value = {
        "principal_id": admin_principal_id,
        "workspace_id": workspace_id,
        "local_card_id": local_card_id,
    }
    update_res = MagicMock()
    proj_check_res = MagicMock()
    proj_check_res.first.return_value = (uuid.uuid4(),)

    mock_session.execute.side_effect = [consume_res, update_res, proj_check_res]

    async def fake_bind(session: AsyncSession, ctx: RLSContext) -> None:
        pass

    monkeypatch.setattr("kanban.auth.setup.bind_rls_context", fake_bind)

    p_id, ws_id, card_id = await service.claim_initial_admin(
        mock_session,
        token=generate_setup_token(),
        username="admin",
        display_name="Admin User",
        email="admin@example.com",
        password="ValidPassword123!",
    )
    assert p_id == str(admin_principal_id)
    assert ws_id == str(workspace_id)
    assert card_id == str(local_card_id)


def test_resolve_key_material_loads_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When key_material is None, _resolve_key_material loads and caches it."""
    mock_factory = MagicMock()
    service = SetupBootstrapService(session_factory=mock_factory, key_material=None)

    loaded_km = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_load = MagicMock(return_value=loaded_km)
    monkeypatch.setattr("kanban.auth.setup.load_key_material", mock_load)

    res1 = service._resolve_key_material()
    res2 = service._resolve_key_material()
    assert res1 == loaded_km
    assert res2 == loaded_km
    mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_mint_token_uses_settings_effective_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When settings is provided, mint_token_if_uninitialized uses settings.effective_origin."""
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    mock_settings = MagicMock()
    mock_settings.effective_origin = "https://custom-origin.local:9000"

    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = True
    mock_session.execute.return_value = mock_res

    class FakeSessionFactory:
        def session(self, ctx: object) -> object:
            class FakeCM:
                async def __aenter__(self) -> AsyncSession:
                    return mock_session

                async def __aexit__(self, exc_type: object, exc_val: object, tb: object) -> None:
                    pass

            return FakeCM()

    token_file = tmp_path / "custom_setup_token"
    monkeypatch.setenv("KB_SETUP_TOKEN_FILE", str(token_file))

    service = SetupBootstrapService(
        session_factory=FakeSessionFactory(),  # type: ignore[arg-type]
        key_material=key_material,
        settings=mock_settings,
    )

    stdout_buf = io.StringIO()
    raw_token = await service.mint_token_if_uninitialized(stdout=stdout_buf)
    assert raw_token is not None
    assert "https://custom-origin.local:9000/setup?token=" in stdout_buf.getvalue()

