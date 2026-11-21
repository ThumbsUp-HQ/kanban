# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Plane database direct exporter and MinIO SigV4 asset streamer (KB-MIGRATION-PLANE-DB-01, S1.3)."""
# ruff: noqa: E501, C901, PLR0911, PLR0912, PLR0915, S108

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlparse

import asyncpg  # type: ignore[import-untyped]
import httpx

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES: int = 25 * 1024 * 1024  # 25 MiB hard cap per attachment
SECRET_IN_ARGV_FORBIDDEN_MSG: str = (
    "Error: SECRET_IN_ARGV_FORBIDDEN: Passing database or MinIO secrets as command-line arguments "
    "is strictly forbidden. Use environment variables (e.g. PLANE_DATABASE_URL) or mode 0600 secret files."
)


class PlaneExportError(Exception):
    """Base exception for Plane export failures."""


class PlaneExportSecurityError(PlaneExportError):
    """Raised when insecure permissions or secret arguments are detected."""


def check_forbidden_exporter_args(argv: Sequence[str]) -> bool:
    """Return True if any forbidden secret parameter is found in argv."""
    forbidden_prefixes = (
        "--password",
        "--secret",
        "--key",
        "--passphrase",
        "--database-url",
        "--db-url",
        "--plane-database-url",
        "--access-key",
        "--secret-key",
        "--minio-secret",
    )
    for arg in argv:
        clean = arg.lower()
        if clean in forbidden_prefixes or any(
            clean.startswith(f"{p}=") for p in forbidden_prefixes
        ):
            return True
    return False


def read_secret_source(
    env_var_name: str,
    file_source: str | Path | None = None,
) -> str | None:
    """Read secret value strictly from environment variable or 0600 file path."""
    val = os.environ.get(env_var_name)
    if val:
        return val.strip()

    if file_source is None:
        file_path_str = os.environ.get(f"{env_var_name}_FILE")
        if not file_path_str:
            return None
        path = Path(file_path_str).resolve()
    elif isinstance(file_source, Path):
        path = file_source.resolve()
    else:
        file_env_val = os.environ.get(file_source)
        if file_env_val:
            path = Path(file_env_val).resolve()
        else:
            path = Path(file_source).resolve()

    if not path.is_file():
        msg = f"Secret file for {env_var_name} does not exist: {path}"
        raise PlaneExportError(msg)

    # Enforce strict 0600 permissions: no permissions for group or others
    st = path.stat()
    mode = st.st_mode & 0o777
    if mode & 0o077 != 0:
        msg = (
            f"Secret file {path} for {env_var_name} has insecure permissions {oct(mode)}: "
            "must be 0600 (owner read/write only)."
        )
        raise PlaneExportSecurityError(msg)

    content = path.read_text(encoding="utf-8").strip()
    return content or None


class MinioSigV4Downloader:
    """Zero-new-dependency pure-stdlib AWS S3 SigV4 streamer for MinIO object downloads."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str | None,
        secret_key: str | None,
        region: str = "us-east-1",
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.timeout = timeout

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(
        self, key: str, date_stamp: str, region_name: str, service_name: str
    ) -> bytes:
        k_date = self._sign(("AWS4" + key).encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, region_name)
        k_service = self._sign(k_region, service_name)
        return self._sign(k_service, "aws4_request")

    def build_auth_headers(self, method: str, object_key: str) -> dict[str, str]:
        """Compute AWS SigV4 authorization headers."""
        if not self.access_key or not self.secret_key:
            return {}

        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        parsed = urlparse(self.endpoint)
        host = parsed.netloc

        clean_key = object_key.lstrip("/")
        canonical_uri = f"/{self.bucket}/{quote(clean_key, safe='/-_.~')}"
        payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        canonical_headers = (
            f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashed_canonical_request}"

        signing_key = self._get_signature_key(self.secret_key, date_stamp, self.region, "s3")
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        auth_header = (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Authorization": auth_header,
        }

    generate_sigv4_headers = build_auth_headers

    async def stream_object(
        self,
        object_key: str,
        dest_file: Path,
        client: httpx.AsyncClient | None = None,
    ) -> int:
        """Stream object from MinIO to dest_file, strictly capped at 25 MiB."""
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        clean_key = object_key.lstrip("/")
        url = f"{self.endpoint}/{self.bucket}/{quote(clean_key, safe='/-_.~')}"
        headers = self.build_auth_headers("GET", clean_key)

        async def _do_stream(c: httpx.AsyncClient) -> int:
            async with c.stream("GET", url, headers=headers, timeout=self.timeout) as resp:
                if resp.status_code != 200:
                    msg = f"MinIO GET {url} failed with status {resp.status_code}"
                    raise PlaneExportError(msg)
                total_bytes = 0
                with dest_file.open("wb") as f:
                    async for chunk in resp.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > MAX_ATTACHMENT_BYTES:
                            msg = f"Attachment {object_key} exceeds 25 MiB limit ({total_bytes} bytes)"
                            raise PlaneExportSecurityError(msg)
                        f.write(chunk)
                return total_bytes

        if client is not None:
            return await _do_stream(client)
        async with httpx.AsyncClient() as c:
            return await _do_stream(c)

    async def download_object(self, client: httpx.AsyncClient, object_key: str) -> bytes | None:
        """Download object from MinIO with streaming cap at 25 MiB."""
        clean_key = object_key.lstrip("/")
        url = f"{self.endpoint}/{self.bucket}/{quote(clean_key, safe='/-_.~')}"
        headers = self.build_auth_headers("GET", clean_key)

        try:
            async with client.stream("GET", url, headers=headers, timeout=self.timeout) as response:
                if response.status_code != 200:
                    logger.warning("MinIO GET %s returned status %d", url, response.status_code)
                    return None

                chunks: list[bytes] = []
                total_bytes = 0
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > MAX_ATTACHMENT_BYTES:
                        logger.warning(
                            "Attachment %s exceeds %d bytes; capped at 25 MiB.",
                            object_key,
                            MAX_ATTACHMENT_BYTES,
                        )
                        # Cap at MAX_ATTACHMENT_BYTES
                        overflow = total_bytes - MAX_ATTACHMENT_BYTES
                        chunks.append(chunk[:-overflow] if overflow < len(chunk) else b"")
                        break
                    chunks.append(chunk)

                return b"".join(chunks)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MinIO stream error downloading %s: %s", object_key, exc)
            return None


@dataclass
class ExporterConfig:
    """Configuration credentials and parameters for PlaneDbExporter."""

    database_url: str
    out_dir: Path
    workspace_slug: str | None = None
    exclude_project_identifiers: set[str] = field(default_factory=lambda: {"TEST"})
    minio_endpoint: str | None = None
    minio_bucket: str = "plane"
    minio_access_key: str | None = None
    minio_secret_key: str | None = None


PlaneExportConfig = ExporterConfig


def resolve_exporter_config(
    out_dir: Path | str,
    workspace_slug: str | None = None,
    exclude_project_identifiers: set[str] | list[str] | str | None = None,
) -> ExporterConfig:
    """Resolve exporter configuration from environment variables or 0600 secret files."""
    db_url = read_secret_source("PLANE_DATABASE_URL")
    if not db_url:
        msg = (
            "PLANE_DATABASE_URL (or PLANE_DATABASE_URL_FILE) must be set in environment "
            "to execute dump-db."
        )
        raise PlaneExportError(msg)

    minio_ep = read_secret_source("PLANE_MINIO_ENDPOINT")
    if not minio_ep:
        msg = (
            "PLANE_MINIO_ENDPOINT (or PLANE_MINIO_ENDPOINT_FILE) must be set in environment "
            "to execute dump-db."
        )
        raise PlaneExportError(msg)
    minio_bkt = read_secret_source("PLANE_MINIO_BUCKET") or "plane"
    minio_ak = read_secret_source("PLANE_MINIO_ACCESS_KEY")
    minio_sk = read_secret_source("PLANE_MINIO_SECRET_KEY")

    if isinstance(exclude_project_identifiers, str):
        excludes = {x.strip().upper() for x in exclude_project_identifiers.split(",") if x.strip()}
    elif isinstance(exclude_project_identifiers, (set, list)):
        excludes = {str(x).strip().upper() for x in exclude_project_identifiers if str(x).strip()}
    else:
        excludes = {"TEST"}

    return ExporterConfig(
        database_url=db_url,
        out_dir=Path(out_dir).resolve(),
        workspace_slug=workspace_slug,
        exclude_project_identifiers=excludes,
        minio_endpoint=minio_ep,
        minio_bucket=minio_bkt,
        minio_access_key=minio_ak,
        minio_secret_key=minio_sk,
    )


class PlaneDbExporter:
    """Direct PostgreSQL and MinIO exporter extracting lossless Plane snapshot bundles."""

    def __init__(self, config: ExporterConfig) -> None:
        self.config = config

    async def export(self) -> dict[str, Any]:
        """Execute extraction inside Repeatable Read Read-Only transaction."""
        self.config.out_dir.mkdir(parents=True, exist_ok=True)

        minio_downloader: MinioSigV4Downloader | None = None
        if self.config.minio_endpoint:
            minio_downloader = MinioSigV4Downloader(
                endpoint=self.config.minio_endpoint,
                bucket=self.config.minio_bucket,
                access_key=self.config.minio_access_key,
                secret_key=self.config.minio_secret_key,
            )

        # Normalize asyncpg URL (strip postgresql+asyncpg:// if present)
        pg_dsn = self.config.database_url
        if "+asyncpg" in pg_dsn:
            pg_dsn = pg_dsn.replace("+asyncpg", "")

        conn = await asyncpg.connect(pg_dsn)
        try:
            # Begin REPEATABLE READ READ ONLY transaction
            tr = conn.transaction(isolation="repeatable_read", readonly=True)
            await tr.start()
            try:
                summary = await self._export_transactional(conn, minio_downloader)
                await tr.commit()
                return summary
            except Exception:
                await tr.rollback()
                raise
        finally:
            await conn.close()

    async def _export_transactional(
        self,
        conn: asyncpg.Connection,
        minio_downloader: MinioSigV4Downloader | None,
    ) -> dict[str, Any]:
        # 1. Resolve Workspaces
        if self.config.workspace_slug:
            ws_rows = await conn.fetch(
                "SELECT id, name, slug FROM workspaces WHERE slug = $1 AND deleted_at IS NULL",
                self.config.workspace_slug,
            )
        else:
            ws_rows = await conn.fetch(
                "SELECT id, name, slug FROM workspaces WHERE deleted_at IS NULL ORDER BY created_at ASC"
            )

        if not ws_rows:
            msg = f"No active Plane workspaces found (slug filter: {self.config.workspace_slug})."
            raise PlaneExportError(msg)

        total_projects = 0
        total_issues = 0
        total_comments = 0
        total_attachments = 0

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            for ws in ws_rows:
                ws_id = ws["id"]
                ws_slug = ws["slug"]

                # 2. Resolve Projects in Workspace
                proj_rows = await conn.fetch(
                    "SELECT id, identifier, name, description, network "
                    "FROM projects WHERE workspace_id = $1 AND deleted_at IS NULL "
                    "ORDER BY identifier ASC",
                    ws_id,
                )

                filtered_projects = [
                    p
                    for p in proj_rows
                    if p["identifier"].upper() not in self.config.exclude_project_identifiers
                ]

                if not filtered_projects:
                    continue

                # 3. Workspace Members
                members_data = await self._export_members(conn, ws_id)

                for proj in filtered_projects:
                    p_id = proj["id"]
                    p_ident = proj["identifier"]

                    # Export per-workspace/per-project PlaneBundle directory
                    proj_bundle_dir = self.config.out_dir / ws_slug / p_ident

                    proj_bundle_dir.mkdir(parents=True, exist_ok=True)
                    att_dir = proj_bundle_dir / "attachments"
                    att_dir.mkdir(parents=True, exist_ok=True)

                    # Export Project metadata
                    project_dict = {
                        "id": str(p_id),
                        "identifier": p_ident,
                        "name": proj["name"],
                        "description": proj["description"] or "",
                        "network": proj["network"]
                        if "network" in proj and proj["network"] is not None
                        else 2,
                    }
                    (proj_bundle_dir / "project.json").write_text(
                        json.dumps([project_dict], indent=2), encoding="utf-8"
                    )

                    # Export States
                    states_data = await self._export_states(conn, p_id)
                    (proj_bundle_dir / "states.json").write_text(
                        json.dumps(states_data, indent=2), encoding="utf-8"
                    )

                    # Export Labels
                    labels_data = await self._export_labels(conn, p_id)
                    (proj_bundle_dir / "labels.json").write_text(
                        json.dumps(labels_data, indent=2), encoding="utf-8"
                    )

                    # Export Cycles
                    cycles_data = await self._export_cycles(conn, p_id)
                    (proj_bundle_dir / "cycles.json").write_text(
                        json.dumps(cycles_data, indent=2), encoding="utf-8"
                    )

                    # Export Modules
                    modules_data = await self._export_modules(conn, p_id)
                    (proj_bundle_dir / "modules.json").write_text(
                        json.dumps(modules_data, indent=2), encoding="utf-8"
                    )

                    # Export Issues with joined relations
                    issues_data, issue_ids = await self._export_issues(conn, p_id)
                    (proj_bundle_dir / "issues.json").write_text(
                        json.dumps(issues_data, indent=2), encoding="utf-8"
                    )

                    # Export Comments
                    comments_data = await self._export_comments(conn, issue_ids)
                    (proj_bundle_dir / "comments.json").write_text(
                        json.dumps(comments_data, indent=2), encoding="utf-8"
                    )

                    # Export Relations
                    relations_data = await self._export_relations(conn, issue_ids)
                    (proj_bundle_dir / "relations.json").write_text(
                        json.dumps(relations_data, indent=2), encoding="utf-8"
                    )

                    # Export Members
                    (proj_bundle_dir / "members.json").write_text(
                        json.dumps(members_data, indent=2), encoding="utf-8"
                    )

                    # Export Attachments from MinIO
                    downloaded_cnt = await self._export_attachments(
                        conn=conn,
                        http_client=http_client,
                        minio_downloader=minio_downloader,
                        p_id=p_id,
                        issues_data=issues_data,
                        comments_data=comments_data,
                        att_dir=att_dir,
                    )

                    total_projects += 1
                    total_issues += len(issues_data)
                    total_comments += len(comments_data)
                    total_attachments += downloaded_cnt

        return {
            "projects_exported": total_projects,
            "issues_exported": total_issues,
            "comments_exported": total_comments,
            "attachments_exported": total_attachments,
            "out_dir": str(self.config.out_dir),
        }

    async def _export_members(self, conn: asyncpg.Connection, ws_id: Any) -> list[dict[str, Any]]:
        # Omit password, token, and secret columns strictly
        query = """
        SELECT u.id, u.email, u.first_name, u.last_name, u.display_name, wm.role
        FROM users u
        JOIN workspace_members wm ON u.id = wm.member_id
        WHERE wm.workspace_id = $1 AND wm.deleted_at IS NULL AND u.deleted_at IS NULL
        ORDER BY u.email ASC
        """
        rows = await conn.fetch(query, ws_id)
        result: list[dict[str, Any]] = []
        for r in rows:
            first = r["first_name"] if "first_name" in r and r["first_name"] else ""
            last = r["last_name"] if "last_name" in r and r["last_name"] else ""
            disp = r["display_name"] if "display_name" in r and r["display_name"] else ""
            if not disp:
                disp = f"{first} {last}".strip() or r["email"]
            result.append(
                {
                    "id": str(r["id"]),
                    "email": r["email"],
                    "first_name": first,
                    "last_name": last,
                    "display_name": disp,
                    "role": r["role"] if "role" in r else 20,
                }
            )
        return result

    async def _export_states(self, conn: asyncpg.Connection, p_id: Any) -> list[dict[str, Any]]:
        query = """
        SELECT id, name, color, "group", sequence, project_id
        FROM states
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY sequence ASC, name ASC
        """
        rows = await conn.fetch(query, p_id)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "color": r["color"] if "color" in r and r["color"] else "#A3A3A3",
                "group": (r["group"] or "unstarted").lower()
                if "group" in r and r["group"]
                else "unstarted",
                "sequence": r["sequence"] if "sequence" in r and r["sequence"] is not None else 0,
                "project": str(r["project_id"])
                if "project_id" in r and r["project_id"]
                else str(p_id),
            }
            for r in rows
        ]

    async def _export_labels(self, conn: asyncpg.Connection, p_id: Any) -> list[dict[str, Any]]:
        query = """
        SELECT id, name, color, project_id
        FROM labels
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY name ASC
        """
        rows = await conn.fetch(query, p_id)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "color": r["color"] if "color" in r and r["color"] else "#3B82F6",
                "project": str(r["project_id"])
                if "project_id" in r and r["project_id"]
                else str(p_id),
            }
            for r in rows
        ]

    async def _export_cycles(self, conn: asyncpg.Connection, p_id: Any) -> list[dict[str, Any]]:
        query = """
        SELECT id, name, description, start_date, end_date, status, project_id
        FROM cycles
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY start_date ASC NULLS LAST, name ASC
        """
        rows = await conn.fetch(query, p_id)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "description": r["description"] if "description" in r and r["description"] else "",
                "start_date": str(r["start_date"])
                if "start_date" in r and r["start_date"]
                else None,
                "end_date": str(r["end_date"]) if "end_date" in r and r["end_date"] else None,
                "status": (r["status"] or "upcoming").lower()
                if "status" in r and r["status"]
                else "upcoming",
                "project": str(r["project_id"])
                if "project_id" in r and r["project_id"]
                else str(p_id),
            }
            for r in rows
        ]

    async def _export_modules(self, conn: asyncpg.Connection, p_id: Any) -> list[dict[str, Any]]:
        query = """
        SELECT id, name, description, status, lead_id, start_date, target_date, project_id
        FROM modules
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY name ASC
        """
        rows = await conn.fetch(query, p_id)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "description": r["description"] if "description" in r and r["description"] else "",
                "status": r["status"] if "status" in r and r["status"] else "planned",
                "lead": str(r["lead_id"]) if "lead_id" in r and r["lead_id"] else None,
                "start_date": str(r["start_date"])
                if "start_date" in r and r["start_date"]
                else None,
                "target_date": str(r["target_date"])
                if "target_date" in r and r["target_date"]
                else None,
                "project": str(r["project_id"])
                if "project_id" in r and r["project_id"]
                else str(p_id),
            }
            for r in rows
        ]

    async def _export_issues(
        self, conn: asyncpg.Connection, p_id: Any
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        query = """
        SELECT id, sequence_id, name, description_html, description_stripped, state_id,
               priority, parent_id, project_id, created_by_id, created_at, updated_at,
               start_date, target_date, archived_at
        FROM issues
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY sequence_id ASC
        """
        rows = await conn.fetch(query, p_id)
        issue_ids = [r["id"] for r in rows]

        if not issue_ids:
            return [], []

        # Join sub-tables: cycle_issues, module_issues, issue_labels, issue_assignees
        cycle_map: dict[str, str] = {}
        try:
            c_rows = await conn.fetch(
                "SELECT issue_id, cycle_id FROM cycle_issues WHERE issue_id = ANY($1) AND deleted_at IS NULL",
                issue_ids,
            )
            for cr in c_rows:
                cycle_map[str(cr["issue_id"])] = str(cr["cycle_id"])
        except Exception:  # noqa: BLE001
            pass

        module_map: dict[str, str] = {}
        try:
            m_rows = await conn.fetch(
                "SELECT issue_id, module_id FROM module_issues WHERE issue_id = ANY($1) AND deleted_at IS NULL",
                issue_ids,
            )
            for mr in m_rows:
                module_map[str(mr["issue_id"])] = str(mr["module_id"])
        except Exception:  # noqa: BLE001
            pass

        label_map: dict[str, list[str]] = {}
        try:
            lbl_rows = await conn.fetch(
                "SELECT issue_id, label_id FROM issue_labels WHERE issue_id = ANY($1) AND deleted_at IS NULL",
                issue_ids,
            )
            for lr in lbl_rows:
                label_map.setdefault(str(lr["issue_id"]), []).append(str(lr["label_id"]))
        except Exception:  # noqa: BLE001
            pass

        assignee_map: dict[str, list[str]] = {}
        try:
            ass_rows = await conn.fetch(
                "SELECT issue_id, assignee_id FROM issue_assignees WHERE issue_id = ANY($1) AND deleted_at IS NULL",
                issue_ids,
            )
            for ar in ass_rows:
                assignee_map.setdefault(str(ar["issue_id"]), []).append(str(ar["assignee_id"]))
        except Exception:  # noqa: BLE001
            pass

        issues_data: list[dict[str, Any]] = []
        for r in rows:
            i_id_str = str(r["id"])
            c_at = (
                r.get("created_at")
                if hasattr(r, "get")
                else (r["created_at"] if "created_at" in r else None)
            )
            u_at = (
                r.get("updated_at")
                if hasattr(r, "get")
                else (r["updated_at"] if "updated_at" in r else None)
            )
            a_at = (
                r.get("archived_at")
                if hasattr(r, "get")
                else (r["archived_at"] if "archived_at" in r else None)
            )
            c_at_str = (
                c_at.isoformat()
                if c_at is not None and hasattr(c_at, "isoformat")
                else (str(c_at) if c_at else None)
            )
            u_at_str = (
                u_at.isoformat()
                if u_at is not None and hasattr(u_at, "isoformat")
                else (str(u_at) if u_at else None)
            )
            a_at_str = (
                a_at.isoformat()
                if a_at is not None and hasattr(a_at, "isoformat")
                else (str(a_at) if a_at else None)
            )

            issues_data.append(
                {
                    "id": i_id_str,
                    "sequence_id": r["sequence_id"],
                    "name": r["name"],
                    "description_html": r["description_html"] if "description_html" in r else "",
                    "description_stripped": r["description_stripped"]
                    if "description_stripped" in r
                    else "",
                    "state_id": str(r["state_id"]) if "state_id" in r and r["state_id"] else None,
                    "priority": (r["priority"] or "none").lower()
                    if "priority" in r and r["priority"]
                    else "none",
                    "parent_id": str(r["parent_id"])
                    if "parent_id" in r and r["parent_id"]
                    else None,
                    "cycle_id": cycle_map.get(i_id_str),
                    "module_id": module_map.get(i_id_str),
                    "labels": label_map.get(i_id_str, []),
                    "assignees": assignee_map.get(i_id_str, []),
                    "created_by": str(r["created_by_id"])
                    if "created_by_id" in r and r["created_by_id"]
                    else None,
                    "created_at": c_at_str,
                    "updated_at": u_at_str,
                    "archived_at": a_at_str,
                    "start_date": str(r["start_date"])
                    if "start_date" in r and r["start_date"]
                    else None,
                    "target_date": str(r["target_date"])
                    if "target_date" in r and r["target_date"]
                    else None,
                    "project": str(r["project_id"])
                    if "project_id" in r and r["project_id"]
                    else str(p_id),
                }
            )

        return issues_data, issue_ids

    async def _export_comments(
        self, conn: asyncpg.Connection, issue_ids: list[Any]
    ) -> list[dict[str, Any]]:
        if not issue_ids:
            return []
        query = """
        SELECT id, issue_id, comment_html, comment_json, actor_id, parent_comment_id, created_at
        FROM issue_comments
        WHERE issue_id = ANY($1) AND deleted_at IS NULL
        ORDER BY created_at ASC
        """
        rows = await conn.fetch(query, issue_ids)
        result: list[dict[str, Any]] = []
        for r in rows:
            c_at = (
                r.get("created_at")
                if hasattr(r, "get")
                else (r["created_at"] if "created_at" in r else None)
            )
            c_at_str = (
                c_at.isoformat()
                if c_at is not None and hasattr(c_at, "isoformat")
                else (str(c_at) if c_at else None)
            )
            result.append(
                {
                    "id": str(r["id"]),
                    "issue_id": str(r["issue_id"]),
                    "comment_html": r["comment_html"] if "comment_html" in r else "",
                    "comment_json": r["comment_json"]
                    if "comment_json" in r and r["comment_json"]
                    else None,
                    "actor": str(r["actor_id"]) if "actor_id" in r and r["actor_id"] else None,
                    "created_by": str(r["actor_id"]) if "actor_id" in r and r["actor_id"] else None,
                    "parent_comment": str(r["parent_comment_id"])
                    if "parent_comment_id" in r and r["parent_comment_id"]
                    else None,
                    "created_at": c_at_str,
                }
            )
        return result

    async def _export_relations(
        self, conn: asyncpg.Connection, issue_ids: list[Any]
    ) -> list[dict[str, Any]]:
        if not issue_ids:
            return []
        query = """
        SELECT id, issue_id, related_issue_id, relation_type
        FROM issue_relations
        WHERE issue_id = ANY($1) AND deleted_at IS NULL
        """
        rows = await conn.fetch(query, issue_ids)
        return [
            {
                "id": str(r["id"]),
                "issue_id": str(r["issue_id"]),
                "related_issue_id": str(r["related_issue_id"]),
                "relation_type": r["relation_type"] or "relates_to",
            }
            for r in rows
        ]

    async def _export_attachments(
        self,
        conn: asyncpg.Connection,
        http_client: httpx.AsyncClient,
        minio_downloader: MinioSigV4Downloader | None,
        p_id: Any,
        issues_data: list[dict[str, Any]],
        comments_data: list[dict[str, Any]],
        att_dir: Path,
    ) -> int:
        asset_keys: dict[str, str] = {}  # key -> filename

        # 1. Inspect file_assets table if it exists in Plane DB
        try:
            asset_rows = await conn.fetch(
                "SELECT id, key, name FROM file_assets WHERE project_id = $1 AND deleted_at IS NULL",
                p_id,
            )
            for ar in asset_rows:
                k = ar["key"]
                fn = ar["name"] or Path(k).name
                asset_keys[k] = fn
        except Exception:  # noqa: BLE001
            # file_assets table might not exist
            pass

        # 2. Extract asset references from HTML bodies
        asset_pattern = re.compile(
            r"""(?:href|src)=['"]([^'"]*(?:/api/assets/v1/workspace/|uploads/)[^'"]+)['"]""",
            re.IGNORECASE,
        )
        for iss in issues_data:
            desc = iss.get("description_html") or ""
            for match in asset_pattern.finditer(desc):
                full_url = match.group(1)
                fn = Path(full_url.split("?")[0]).name
                if fn and full_url not in asset_keys:
                    asset_keys[full_url] = fn

        for comm in comments_data:
            c_html = comm.get("comment_html") or ""
            for match in asset_pattern.finditer(c_html):
                full_url = match.group(1)
                fn = Path(full_url.split("?")[0]).name
                if fn and full_url not in asset_keys:
                    asset_keys[full_url] = fn

        if not asset_keys or not minio_downloader:
            return 0

        manifest: list[dict[str, Any]] = []
        downloaded_count = 0

        for obj_key, orig_fn in asset_keys.items():
            # Derive safe local filename
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", orig_fn)
            if not safe_name:
                safe_name = f"attachment-{uuid.uuid4().hex[:8]}"

            dest_file = att_dir / safe_name
            # Prevent overwriting distinct keys with same name
            if dest_file.exists():
                prefix = hashlib.sha256(obj_key.encode("utf-8")).hexdigest()[:8]
                safe_name = f"{prefix}_{safe_name}"
                dest_file = att_dir / safe_name

            raw_bytes = await minio_downloader.download_object(http_client, obj_key)
            if raw_bytes is not None:
                dest_file.write_bytes(raw_bytes)
                downloaded_count += 1
                manifest.append(
                    {
                        "original_key": obj_key,
                        "original_filename": orig_fn,
                        "saved_filename": safe_name,
                        "byte_size": len(raw_bytes),
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    }
                )

        if manifest:
            (att_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return downloaded_count
