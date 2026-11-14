# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Plane snapshot & API client with hardened SSRF defenses (KB-P6-01, S1.3, S15.5)."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES: int = 25 * 1024 * 1024  # 25 MiB limit per page / attachment
DEFAULT_TIMEOUT_SECONDS: float = 15.0


class PlaneClientError(Exception):
    """Base exception for Plane client and bundle reading failures."""


class PlaneSecurityError(PlaneClientError):
    """Raised when an SSRF, invalid scheme, or unsafe network condition is detected."""


class PlaneProject(BaseModel):
    """Pydantic model representing a Plane Project."""

    model_config = ConfigDict(extra="ignore")

    id: str
    identifier: str
    name: str
    description: str | None = None
    network: int | str | None = None


class PlaneState(BaseModel):
    """Pydantic model representing a Plane Workflow State."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    color: str | None = None
    group: str = "unstarted"  # backlog, unstarted, started, completed, cancelled
    sequence: int | None = 0
    project: str | None = None


class PlaneLabel(BaseModel):
    """Pydantic model representing a Plane Label."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    color: str | None = None
    project: str | None = None


class PlaneCycle(BaseModel):
    """Pydantic model representing a Plane Cycle."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str = "upcoming"  # upcoming, active, completed
    project: str | None = None


class PlaneModule(BaseModel):
    """Pydantic model representing a Plane Module."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str | None = None
    status: str | None = None
    lead: str | None = None
    start_date: str | None = None
    target_date: str | None = None
    project: str | None = None


class PlaneIssue(BaseModel):
    """Pydantic model representing a Plane Issue."""

    model_config = ConfigDict(extra="ignore")

    id: str
    sequence_id: int
    name: str
    description_html: str | None = None
    description_stripped: str | None = None
    state_id: str | None = None
    state: str | None = None
    priority: str | None = "none"  # urgent, high, medium, low, none
    parent: str | None = None
    parent_id: str | None = None
    cycle_id: str | None = None
    cycle: str | None = None
    module_id: str | None = None
    module: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    start_date: str | None = None
    target_date: str | None = None
    project: str | None = None


class PlaneComment(BaseModel):
    """Pydantic model representing a Plane Comment."""

    model_config = ConfigDict(extra="ignore")

    id: str
    issue_id: str | None = None
    issue: str | None = None
    comment_html: str | None = None
    comment_json: Any | None = None
    actor: str | None = None
    created_by: str | None = None
    created_at: str | None = None


class PlaneRelation(BaseModel):
    """Pydantic model representing a Plane Issue Relation/Link."""

    model_config = ConfigDict(extra="ignore")

    id: str
    issue: str | None = None
    issue_id: str | None = None
    related_issue: str | None = None
    related_issue_id: str | None = None
    relation_type: str = "relates_to"  # blocking, blocked_by, relates_to, duplicate


class PlaneMember(BaseModel):
    """Pydantic model representing a Plane Workspace/Project Member."""

    model_config = ConfigDict(extra="ignore")

    id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    role: Any | None = None


@dataclass
class PlaneBundle:
    """In-memory bundle of parsed Plane export artifacts."""

    projects: list[PlaneProject] = field(default_factory=list)
    states: list[PlaneState] = field(default_factory=list)
    labels: list[PlaneLabel] = field(default_factory=list)
    cycles: list[PlaneCycle] = field(default_factory=list)
    modules: list[PlaneModule] = field(default_factory=list)
    issues: list[PlaneIssue] = field(default_factory=list)
    comments: list[PlaneComment] = field(default_factory=list)
    relations: list[PlaneRelation] = field(default_factory=list)
    members: list[PlaneMember] = field(default_factory=list)
    attachments: dict[str, bytes] = field(default_factory=dict)


T = TypeVar("T", bound=BaseModel)


def _validate_scheme(
    scheme: str,
    url: str,
    *,
    allow_loopback_http: bool,
    is_loopback_host: bool,
) -> None:
    if scheme == "http":
        if not (allow_loopback_http and is_loopback_host):
            msg = f"HTTP scheme forbidden for remote Plane target: {url!r}. HTTPS is required."
            raise PlaneSecurityError(msg)
    elif scheme != "https":
        msg = f"Unsupported URL scheme: {scheme!r}. Must be HTTPS."
        raise PlaneSecurityError(msg)


def _check_ip_security(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_loopback_http: bool,
    is_loopback_host: bool,
) -> None:
    ip_str = str(ip_obj)
    if ip_obj.is_loopback:
        if not (allow_loopback_http and is_loopback_host):
            msg = f"Target resolved to loopback IP {ip_str}, which is blocked."
            raise PlaneSecurityError(msg)
    elif ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
        msg = f"Target resolved to blocked private/reserved IP {ip_str}."
        raise PlaneSecurityError(msg)


def validate_target_url(
    url: str,
    *,
    allow_loopback_http: bool = False,
    allow_private_cidr: bool = False,
) -> tuple[str, list[str]]:
    """Validate URL scheme and resolve target hostname with strict SSRF defenses."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname

    if not hostname:
        msg = f"Invalid URL: missing hostname in {url!r}"
        raise PlaneSecurityError(msg)

    is_loopback_host = hostname in ("localhost", "127.0.0.1", "::1")
    _validate_scheme(
        scheme,
        url,
        allow_loopback_http=allow_loopback_http,
        is_loopback_host=is_loopback_host,
    )

    port = parsed.port or (443 if scheme == "https" else 80)
    resolved_ips: list[str] = []

    try:
        ip_obj = ipaddress.ip_address(hostname)
        ip_list = [ip_obj]
    except ValueError:
        try:
            addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            ip_list = [ipaddress.ip_address(info[4][0]) for info in addr_infos]
        except socket.gaierror as exc:
            msg = f"DNS resolution failed for hostname {hostname!r}: {exc}"
            raise PlaneSecurityError(msg) from exc

    for ip_item in ip_list:
        ip_str = str(ip_item)
        resolved_ips.append(ip_str)

        if not allow_private_cidr:
            _check_ip_security(
                ip_item,
                allow_loopback_http=allow_loopback_http,
                is_loopback_host=is_loopback_host,
            )

    return hostname, resolved_ips


class PlaneClient:
    """Client for reading exported Plane bundles or fetching snapshots via live API."""

    def __init__(
        self,
        *,
        allow_loopback_http: bool = False,
        allow_private_cidr: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize PlaneClient with security flags and timeout."""
        self.allow_loopback_http = allow_loopback_http
        self.allow_private_cidr = allow_private_cidr
        self.timeout_seconds = timeout_seconds

    def _load_entities(self, dir_path: Path, filename: str, model_cls: type[T]) -> list[T]:
        f = dir_path / filename
        if not f.is_file():
            return []
        data = self._read_json_file(f)
        items = data if isinstance(data, list) else [data]
        return [model_cls.model_validate(item) for item in items]

    def _load_flexible_entities(
        self, dir_path: Path, base_name: str, model_cls: type[T]
    ) -> list[T]:
        single_file = dir_path / f"{base_name}.json"
        multi_dir = dir_path / base_name
        results: list[T] = []
        if single_file.is_file():
            data = self._read_json_file(single_file)
            items = data if isinstance(data, list) else [data]
            results.extend(model_cls.model_validate(item) for item in items)
        elif multi_dir.is_dir():
            for p in sorted(multi_dir.glob("*.json")):
                data = self._read_json_file(p)
                items = data if isinstance(data, list) else [data]
                results.extend(model_cls.model_validate(item) for item in items)
        return results

    def _load_attachments(self, dir_path: Path) -> dict[str, bytes]:
        attachments_dir = dir_path / "attachments"
        att_dict: dict[str, bytes] = {}
        if not attachments_dir.is_dir():
            return att_dict
        for att_file in attachments_dir.glob("*"):
            if att_file.is_file():
                if att_file.stat().st_size > MAX_PAGE_BYTES:
                    msg = f"Attachment {att_file.name} exceeds maximum allowable size of 25 MiB."
                    raise PlaneClientError(msg)
                att_dict[att_file.name] = att_file.read_bytes()
        return att_dict

    def load_bundle_from_dir(self, bundle_dir: Path | str) -> PlaneBundle:
        """Load and validate all Plane JSON entities and attachments from an export directory."""
        dir_path = Path(bundle_dir).resolve()
        if not dir_path.is_dir():
            msg = f"Bundle directory does not exist or is not a directory: {dir_path}"
            raise PlaneClientError(msg)

        proj_file = "project.json" if (dir_path / "project.json").is_file() else "projects.json"
        link_file = "links.json" if (dir_path / "links.json").is_file() else "relations.json"

        return PlaneBundle(
            projects=self._load_entities(dir_path, proj_file, PlaneProject),
            states=self._load_entities(dir_path, "states.json", PlaneState),
            labels=self._load_entities(dir_path, "labels.json", PlaneLabel),
            cycles=self._load_entities(dir_path, "cycles.json", PlaneCycle),
            modules=self._load_entities(dir_path, "modules.json", PlaneModule),
            issues=self._load_flexible_entities(dir_path, "issues", PlaneIssue),
            comments=self._load_flexible_entities(dir_path, "comments", PlaneComment),
            relations=self._load_entities(dir_path, link_file, PlaneRelation),
            members=self._load_entities(dir_path, "members.json", PlaneMember),
            attachments=self._load_attachments(dir_path),
        )

    def _read_json_file(self, file_path: Path) -> object:
        """Read and decode JSON from file enforcing size limits."""
        if file_path.stat().st_size > MAX_PAGE_BYTES:
            msg = f"File {file_path.name} exceeds maximum allowable size of 25 MiB."
            raise PlaneClientError(msg)
        try:
            content = file_path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as exc:
            msg = f"Failed to parse JSON file {file_path}: {exc}"
            raise PlaneClientError(msg) from exc

    async def fetch_snapshot(
        self,
        *,
        base_url: str,
        workspace_slug: str,
        project_identifier: str,
        out_dir: Path | str,
        api_key: str | None = None,
    ) -> Path:
        """Fetch project snapshot from a live Plane instance and save as bundle directory."""
        effective_api_key = api_key or os.environ.get("PLANE_API_KEY")
        if not effective_api_key:
            msg = "PLANE_API_KEY environment variable or api_key parameter is required."
            raise PlaneClientError(msg)

        normalized_base = base_url.rstrip("/")
        validate_target_url(
            normalized_base,
            allow_loopback_http=self.allow_loopback_http,
            allow_private_cidr=self.allow_private_cidr,
        )

        out_path = await asyncio.to_thread(self._prepare_snapshot_dir, out_dir)

        headers = {
            "X-API-Key": effective_api_key,
            "Accept": "application/json",
            "User-Agent": "thumbs-up-kanban-importer/1.0",
        }

        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=self.timeout_seconds,
            read=self.timeout_seconds,
        )

        async with httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=False
        ) as client:
            proj_url = f"/api/v1/workspaces/{workspace_slug}/projects/{project_identifier}/"
            proj_data = await self._get_endpoint(client, normalized_base, proj_url)
            (out_path / "project.json").write_bytes(proj_data)
            project_obj = PlaneProject.model_validate(json.loads(proj_data))
            project_id = project_obj.id

            proj_prefix = f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}"
            endpoints = [
                (f"{proj_prefix}/states/", "states.json"),
                (f"{proj_prefix}/issue-labels/", "labels.json"),
                (f"{proj_prefix}/cycles/", "cycles.json"),
                (f"{proj_prefix}/modules/", "modules.json"),
                (f"{proj_prefix}/issues/", "issues.json"),
                (f"/api/v1/workspaces/{workspace_slug}/members/", "members.json"),
            ]
            for ep_url, ep_file in endpoints:
                ep_data = await self._get_endpoint(client, normalized_base, ep_url)
                (out_path / ep_file).write_bytes(ep_data)

            # Optional links endpoint
            links_url = f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/links/"
            try:
                links_data = await self._get_endpoint(client, normalized_base, links_url)
                (out_path / "links.json").write_bytes(links_data)
            except PlaneClientError:
                (out_path / "links.json").write_text("[]", encoding="utf-8")

            (out_path / "comments.json").write_text("[]", encoding="utf-8")

        return out_path

    @staticmethod
    def _prepare_snapshot_dir(out_dir: Path | str) -> Path:
        out_path = Path(out_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "attachments").mkdir(parents=True, exist_ok=True)
        return out_path

    async def _get_endpoint(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        rel_url: str,
    ) -> bytes:
        http_ok = 200
        http_rate_limit = 429
        max_retries = 3

        url = f"{base_url}{rel_url}"
        validate_target_url(
            url,
            allow_loopback_http=self.allow_loopback_http,
            allow_private_cidr=self.allow_private_cidr,
        )

        for attempt in range(max_retries):
            resp = await client.get(url)
            if resp.status_code in (301, 302, 307, 308):
                msg = f"Redirect rejected for {url}: received status {resp.status_code}"
                raise PlaneSecurityError(msg)
            if resp.status_code == http_rate_limit:
                retry_after_hdr = resp.headers.get("Retry-After")
                delay = float(retry_after_hdr) if retry_after_hdr else (2.0**attempt)
                await asyncio.sleep(min(delay, 10.0))
                continue
            if resp.status_code != http_ok:
                msg = (
                    f"HTTP request to {rel_url} failed with status "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
                raise PlaneClientError(msg)
            content = resp.content
            if len(content) > MAX_PAGE_BYTES:
                msg = f"Response from {rel_url} exceeded 25 MiB limit."
                raise PlaneClientError(msg)
            return content
        msg = f"Exceeded max retries for {rel_url} due to rate limiting (429)."
        raise PlaneClientError(msg)
