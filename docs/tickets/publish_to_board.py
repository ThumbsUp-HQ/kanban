#!/usr/bin/env python3
"""Idempotent bulk publisher for docs/tickets/KB-*.md -> Plane Kanban board.

Usage:
  1. Dry-run verification (zero network calls):
       python3 docs/tickets/publish_to_board.py --dry-run

  2. Publish to Plane (reads KANBAN_SERVER, KANBAN_WORKSPACE, KANBAN_PROJECT,
     KANBAN_API_KEY from ~/.gemini/config/mcp_config.json or CLI/env):
       python3 docs/tickets/publish_to_board.py --workspace kanban --project KANBA

Safety guarantees:
  - Hard-blocks publishing if target project is 'NETALERTXN'.
  - Publishes Epics (KB-E0..KB-E6) first, then all 144 granular tickets in
    strict Kahn topological order so every dependency already has a real board key.
  - Immediately PATCHes each created ticket's description so `<TICKET_ID>` is
    replaced with its own real board key (e.g. `docs/qa/KANBA-14/`) and every
    `KB-*` prerequisite reference includes its real board key, plus links
    `parent` to the Phase Epic UUID.
  - Checkpoints progress after every single ticket in `docs/tickets/board_mapping.json`
    and updates `docs/tickets/INDEX.md` so interrupted runs resume cleanly.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import yaml

TICKETS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TICKETS_DIR.parent.parent
MAPPING_FILE = TICKETS_DIR / "board_mapping.json"
INDEX_FILE = TICKETS_DIR / "INDEX.md"
PROJECT_GEMINI_SETTINGS = REPO_ROOT / ".gemini" / "settings.json"
MCP_CONFIG_PATH = Path.home() / ".gemini" / "config" / "mcp_config.json"


def load_mcp_defaults() -> dict[str, str]:
    defaults = {
        "server": os.environ.get("KANBAN_SERVER", "https://kanban.hackedyour.info"),
        "workspace": os.environ.get("KANBAN_WORKSPACE", ""),
        "project": os.environ.get("KANBAN_PROJECT", ""),
        "api_key": os.environ.get("KANBAN_API_KEY", ""),
    }
    if PROJECT_GEMINI_SETTINGS.exists():
        proj_cfg = json.loads(PROJECT_GEMINI_SETTINGS.read_text())
        kb = proj_cfg.get("mcpServers", {}).get("kanban", {})
        hdrs = kb.get("headers", {})
        auth = hdrs.get("Authorization", "")
        ws = hdrs.get("X-Workspace-slug") or hdrs.get("X-Workspace-Slug") or ""
        if not defaults["api_key"] and auth.startswith("Bearer "):
            defaults["api_key"] = auth[len("Bearer "):].strip()
        if not defaults["workspace"] and ws:
            defaults["workspace"] = ws
        if not defaults["project"] and ws == "kanban":
            defaults["project"] = "KANBA"
    if MCP_CONFIG_PATH.exists():
        cfg = json.loads(MCP_CONFIG_PATH.read_text())
        env = cfg.get("mcpServers", {}).get("kanban", {}).get("env", {})
        for k, env_k in [
            ("server", "KANBAN_SERVER"),
            ("workspace", "KANBAN_WORKSPACE"),
            ("project", "KANBAN_PROJECT"),
            ("api_key", "KANBAN_API_KEY"),
        ]:
            if not defaults[k] and env.get(env_k):
                defaults[k] = env[env_k]
    return defaults


def markdown_to_html(md: str) -> str:
    proc = subprocess.run(
        ["/usr/bin/pandoc", "-f", "gfm", "-t", "html", "--no-highlight"],
        input=md.encode("utf-8"),
        capture_output=True,
        timeout=10,
        check=True,
    )
    return proc.stdout.decode("utf-8").strip() or "<p></p>"


def load_all_tickets() -> tuple[dict[str, tuple[dict, str]], dict[str, tuple[dict, str]], list[list[str]]]:
    epics: dict[str, tuple[dict, str]] = {}
    tickets: dict[str, tuple[dict, str]] = {}
    for path in sorted(TICKETS_DIR.glob("KB-*.md")):
        raw = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not m:
            raise ValueError(f"Missing YAML frontmatter in {path}")
        fm = yaml.safe_load(m.group(1))
        body = m.group(2).strip()
        tid = fm["id"]
        if tid.startswith("KB-E"):
            epics[tid] = (fm, body)
        else:
            tickets[tid] = (fm, body)

    in_deg = {t: len(tickets[t][0].get("depends_on", [])) for t in tickets}
    dependents: dict[str, list[str]] = defaultdict(list)
    for t, (fm, _) in tickets.items():
        for dep in fm.get("depends_on", []):
            if dep not in tickets:
                raise ValueError(f"{t} depends on unknown {dep}")
            dependents[dep].append(t)

    waves: list[list[str]] = []
    ready = sorted([t for t, d in in_deg.items() if d == 0])
    seen = 0
    while ready:
        waves.append(ready)
        seen += len(ready)
        nxt = []
        for u in ready:
            for v in dependents[u]:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    nxt.append(v)
        ready = sorted(nxt)

    if seen != len(tickets):
        raise ValueError(f"Cycle detected in ticket DAG ({seen}/{len(tickets)})")
    return epics, tickets, waves


def render_final_markdown(local_id: str, real_key: str, body: str, mapping: dict[str, dict]) -> str:
    rendered = body.replace("<TICKET_ID>", real_key)

    def repl_kb(match: re.Match[str]) -> str:
        ref = match.group(0)
        if ref == local_id:
            return f"{real_key} ({local_id})"
        if ref in mapping:
            return f"{mapping[ref]['key']} ({ref})"
        return ref

    rendered = re.sub(r"\bKB-(?:E\d+|P\d+-\d+[ab]?)\b", repl_kb, rendered)
    header = f"> **Architect Spec ID:** `{local_id}` | **Source File:** `docs/tickets/{local_id}.md`\n\n"
    return header + rendered


class PlaneClient:
    def __init__(self, server: str, workspace: str, project_ident: str, api_key: str) -> None:
        self.base = f"{server.rstrip('/')}/api/v1/workspaces/{workspace}"
        self.project_ident = project_ident
        self.api_key = api_key
        self.project_id: str | None = None
        self.actual_identifier: str = project_ident
        self.states: dict[str, str] = {}

    def call(self, endpoint: str, method: str = "GET", data: dict | None = None) -> dict:
        url = f"{self.base}/{endpoint.lstrip('/')}"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "KanbanArchitectPublisher/1.0",
        }
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        for attempt in range(12):
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 11:
                    retry_after = exc.headers.get("Retry-After")
                    wait_s = float(retry_after) + 1.0 if (retry_after and retry_after.isdigit()) else min(62.0, 15.0 * (attempt + 1))
                    print(f"  [rate-limit 429] sleeping {wait_s:.1f}s before retry {attempt + 1}/11...", flush=True)
                    time.sleep(wait_s)
                    continue
                err = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {exc.code} on {method} {url}: {err}") from exc
        raise RuntimeError(f"Exhausted retries on {method} {url}")

    def resolve_project_and_states(self) -> None:
        res = self.call("projects/")
        for proj in res.get("results", []):
            if proj.get("identifier") == self.project_ident or proj.get("name") == self.project_ident:
                self.project_id = proj["id"]
                self.actual_identifier = proj["identifier"]
                break
        if not self.project_id:
            avail = [(p.get("identifier"), p.get("name")) for p in res.get("results", [])]
            raise RuntimeError(f"Project '{self.project_ident}' not found. Available: {avail}")
        st_res = self.call(f"projects/{self.project_id}/states/")
        for st in st_res.get("results", []):
            self.states[st["name"].strip().lower()] = st["id"]


def update_index_md(mapping: dict[str, dict]) -> None:
    if not INDEX_FILE.exists():
        return
    txt = INDEX_FILE.read_text(encoding="utf-8")
    for local_id, info in mapping.items():
        key = info["key"]
        txt = re.sub(
            rf"(\| (?:`{re.escape(local_id)}`|\[\`{re.escape(local_id)}\`\]\(\./{re.escape(local_id)}\.md\)) \| )`TBD`",
            rf"\1`{key}`",
            txt,
        )
    INDEX_FILE.write_text(txt, encoding="utf-8")


def main() -> int:
    defaults = load_mcp_defaults()
    parser = argparse.ArgumentParser(description="Bulk-publish drafted Kanban tickets in topological order.")
    parser.add_argument("--server", default=defaults["server"])
    parser.add_argument("--workspace", default=defaults["workspace"])
    parser.add_argument("--project", default=defaults["project"])
    parser.add_argument("--api-key", default=defaults["api_key"])
    parser.add_argument("--dry-run", action="store_true", help="Validate DAG, pandoc HTML rendering, and order without API calls.")
    parser.add_argument("--delay-ms", type=int, default=1080, help="Polite inter-request pacing in ms (Plane limit is 60 req/min).")
    args = parser.parse_args()

    epics, tickets, waves = load_all_tickets()
    ordered_ids = sorted(epics.keys()) + [tid for wave in waves for tid in wave]

    if args.dry_run:
        sample_html = markdown_to_html(tickets["KB-P0-01"][1])
        print(
            f"[DRY-RUN OK] Verified {len(epics)} Epics + {len(tickets)} Tickets "
            f"({len(ordered_ids)} total items across {len(waves)} parallel waves). "
            f"Pandoc HTML check passed ({len(sample_html)} bytes)."
        )
        print(f"Configured target: server={args.server} workspace={args.workspace!r} project={args.project!r}")
        if args.project.upper() == "NETALERTXN":
            print("NOTE: Target project is still 'NETALERTXN' - repoint KANBAN_WORKSPACE/KANBAN_PROJECT before live run.")
        return 0

    if not args.workspace or not args.project or not args.api_key:
        print("ERROR: --workspace, --project, and --api-key (or MCP config env) are required.", file=sys.stderr)
        return 2
    if args.project.upper() == "NETALERTXN":
        print("ABORTED: Refusing to publish Kanban platform tickets into project 'NETALERTXN'.", file=sys.stderr)
        return 2

    mapping: dict[str, dict] = json.loads(MAPPING_FILE.read_text()) if MAPPING_FILE.exists() else {}
    client = PlaneClient(args.server, args.workspace, args.project, args.api_key)
    client.resolve_project_and_states()
    backlog_state = client.states.get("backlog") or next(iter(client.states.values()), None)

    last_seq = max(
        (int(info["key"].rsplit("-", 1)[-1]) for info in mapping.values() if "-" in info.get("key", "")),
        default=0,
    )

    for idx, local_id in enumerate(ordered_ids, 1):
        if local_id in mapping:
            continue

        fm, body = epics[local_id] if local_id in epics else tickets[local_id]
        title = fm["title"]
        state_id = client.states.get(str(fm.get("state", "Backlog")).lower(), backlog_state)
        predicted_key = f"{client.actual_identifier}-{last_seq + 1}" if last_seq > 0 else "<TICKET_ID>"
        initial_md = render_final_markdown(local_id, predicted_key, body, mapping)
        create_payload: dict = {"name": title, "description_html": markdown_to_html(initial_md)}
        if state_id:
            create_payload["state"] = state_id
        epic_id = fm.get("epic")
        if epic_id and epic_id in mapping:
            create_payload["parent"] = mapping[epic_id]["uuid"]

        created = client.call(f"projects/{client.project_id}/issues/", method="POST", data=create_payload)
        actual_seq = int(created["sequence_id"])
        last_seq = actual_seq
        real_key = f"{client.actual_identifier}-{actual_seq}"
        issue_uuid = created["id"]
        mapping[local_id] = {"key": real_key, "uuid": issue_uuid, "title": title}

        if real_key != predicted_key:
            time.sleep(args.delay_ms / 1000.0)
            final_md = render_final_markdown(local_id, real_key, body, mapping)
            client.call(
                f"projects/{client.project_id}/issues/{issue_uuid}/",
                method="PATCH",
                data={"description_html": markdown_to_html(final_md)},
            )
        MAPPING_FILE.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[{idx}/{len(ordered_ids)}] CREATED {local_id} -> {real_key}: {title}", flush=True)
        time.sleep(args.delay_ms / 1000.0)

    # Final pass: update Epic descriptions so child tables show their newly created board keys too
    for eid in sorted(epics.keys()):
        fm, body = epics[eid]
        info = mapping[eid]
        final_md = render_final_markdown(eid, info["key"], body, mapping)
        client.call(
            f"projects/{client.project_id}/issues/{info['uuid']}/",
            method="PATCH",
            data={"description_html": markdown_to_html(final_md)},
        )
        time.sleep(args.delay_ms / 1000.0)

    update_index_md(mapping)
    print(f"COMPLETE: Published {len(mapping)} items and updated {INDEX_FILE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
