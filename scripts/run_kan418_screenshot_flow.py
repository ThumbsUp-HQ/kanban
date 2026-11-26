# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Zero-Mock Screenshot Orchestrator for KAN-418."""

import asyncio
import os
import subprocess
import time
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from scripts.run_kan418_live_workout import (
    seed_database,
    MASTER_KEK,
    AUTH_PEPPER,
    SESSION_HMAC_KEY,
    _b64,
)

DB_URL = "postgresql+asyncpg://kanban_migrator@/kanban_workout?host=/tmp/kb-pgsock-kan418"

async def ensure_seed():
    print("[Screenshot Prep] Ensuring database seeded...")
    seed_info = await seed_database(DB_URL)

    # Seed 525 DCR clients so governance table pagination shows 500+ clients
    engine = create_async_engine(DB_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        # Check current count
        res = await s.execute(text("SELECT count(*) FROM oauth_clients"))
        count = res.scalar() or 0
        if count < 500:
            print(f"[Screenshot Prep] Seeding additional DCR clients (current={count})...")
            for i in range(525):
                cid = f"client_dcr_stale_{uuid.uuid4().hex[:12]}"
                await s.execute(
                    text(
                        "INSERT INTO oauth_clients (id, client_id, client_name, client_type, redirect_uris, status, created_at) "
                        "VALUES (:id, :cid, :cname, 'public', '{\"https://127.0.0.1/cb\"}'::text[], 'active', NOW() - INTERVAL '30 days')"
                    ),
                    {"id": uuid.uuid4(), "cid": cid, "cname": f"Automated Stale Agent {i+1}"},
                )
            await s.commit()
    await engine.dispose()
    return seed_info

def main():
    seed_info = asyncio.run(ensure_seed())
    cookie_val = seed_info["cookie_val"]
    csrf_token = seed_info["csrf_token"]

    env = os.environ.copy()
    env["KANBAN_DEPLOYMENT_MODE"] = "standalone"
    env["KB_BIND_HOST"] = "127.0.0.1"
    env["KB_BIND_PORT"] = "18418"
    env["KB_PUBLIC_ORIGIN"] = "http://127.0.0.1:18418"
    env["KANBAN_DATABASE_URL"] = "postgresql+asyncpg://kanban_app@/kanban_workout?host=/tmp/kb-pgsock-kan418"
    env["KANBAN_MASTER_KEK"] = _b64(MASTER_KEK)
    env["KANBAN_AUTH_PEPPER"] = _b64(AUTH_PEPPER)
    env["KANBAN_SESSION_HMAC_KEY"] = _b64(SESSION_HMAC_KEY)
    env["KANBAN_MASTER_KEK_KID"] = "test-kid-1"
    env["KAN418_PORT"] = "18418"
    env["KAN418_COOKIE"] = cookie_val
    env["KAN418_CSRF"] = csrf_token

    uv_log = open("/tmp/uvicorn_kan418_screens.log", "w")
    print("[Screenshot Prep] Starting Uvicorn on 127.0.0.1:18418...")
    uv_proc = subprocess.Popen(
        [
            ".venv/bin/python",
            "-m",
            "uvicorn",
            "kanban.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "18418",
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=uv_log,
        stderr=uv_log,
    )

    try:
        # Wait for server to respond
        time.sleep(3)
        print("[Screenshot Prep] Launching Playwright script...")
        res = subprocess.run(
            ["node", "scripts/capture_kan418_screenshots.mjs"],
            env=env,
            check=True,
        )
        print("[Screenshot Prep] Playwright execution complete with code:", res.returncode)
    finally:
        print("[Screenshot Prep] Shutting down Uvicorn...")
        uv_proc.terminate()
        try:
            uv_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            uv_proc.kill()
        uv_log.close()

if __name__ == "__main__":
    main()
