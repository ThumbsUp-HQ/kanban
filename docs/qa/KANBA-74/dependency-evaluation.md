# Dependency Evaluation: pillow==13.0.0 (MIT-CMU)

## 1. Executive Summary & Board Governance
- **Package**: `pillow==13.0.0`
- **License**: `MIT-CMU` (Historical PIL/Pillow permissive license, functionally equivalent to MIT/Apache-2.0, permissive, zero copyleft obligations)
- **Board Approval Citations**:
  - Request: Swarm Message #116 (@builder-22)
  - Security Engineer Review & Approval: Swarm Message #118 (@sec-reviewer)
  - Architectural Review & Approval: Swarm Message #120 (@arch-reviewer)
- **Allowlist Registration**: Approved exception registered in `license-allowlist.toml` with citation to Swarm board decisions #116, #118, #120. `python scripts/license_gate.py` passes with 0 violations.

---

## 2. Supply-Chain Pinning & Cryptographic Hashes
Pinned in `kanban/pyproject.toml` and locked in `uv.lock`:
- **Source Distribution (sdist)**:
  `pillow-13.0.0.tar.gz`: `sha256:cdcd1ba258178f7356d74170c9a81ba4eab6a5d55748bc402a5a2a6fe6be3510`
- **Linux Wheels (CP312 manylinux)**:
  `pillow-13.0.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`: `sha256:42d63be3af4f9b951b199b0a9d23365d37ab14687e6d77b74940432c8515c4ca`
  `pillow-13.0.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl`: `sha256:8bf295fe459343bc6093c8e5e0df60bfa189e0fcb775a22e2c2488fdeccc6c0d`

---

## 3. Supported Codecs & Attack Surface
- **In-Scope Image Formats**:
  - `image/png`: PNG (Portable Network Graphics)
  - `image/jpeg`: JPEG / JFIF
  - `image/webp`: WebP
  - `image/gif`: Graphics Interchange Format (static and animated <= 200 frames)
  - `image/avif`: AV1 Image File Format
  - `image/svg+xml`: Handled via defusedxml / sanitize_svg pipeline, bypassing raster engine.
- **Out-of-Scope Formats**:
  - TIFF, BMP, ICO, TGA, PCX, PSD, EPS are strictly rejected by the magic-byte sniffer (`sniff_media_type`) before Pillow ever touches them.

---

## 4. Decompression Bomb & Resource Exhaustion Defense
- **Image.MAX_IMAGE_PIXELS**: Configured globally to `40_000_000` (40 MP exact, per S5.4).
- **Header Pre-Validation**: Dimensions inspected from image headers before raw bitmap allocation:
  - Width > 16,384 px or Height > 16,384 px -> Rejected with `422 IMAGE_DIMENSIONS_EXCEEDED`.
  - Total pixels (w * h) > 40,000,000 px -> Rejected with `422 IMAGE_DIMENSIONS_EXCEEDED`.
- **Animated Frame Bounds**:
  - Multi-frame animated media capped at `MAX_ANIMATED_FRAMES = 200`.
  - Total animated pixel area across all frames capped at `MAX_ANIMATED_TOTAL_PIXELS = 80_000_000`.
- **Warning Promotion**: `Image.DecompressionBombWarning` is promoted to an exception via `warnings.catch_warnings(action="error")` so decompression bombs never execute silently.
- **Concurrency Isolation**: All raster processing executes in thread workers (`anyio.to_thread.run_sync`) behind an `asyncio.Semaphore(4)` concurrency limiter.
