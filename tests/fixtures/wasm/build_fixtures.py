# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Build reproducible WebAssembly test fixtures for Tier A Wasmtime sandbox (KB-P5-13)."""

from pathlib import Path

import wasmtime

FIXTURES_DIR = Path(__file__).parent

# 1. echo_cvss.wat -> echo_cvss.wasm
# Pre-stores '{"level": "high", "score": 8.8, "label": "8.8 High"}' at offset 1024 (52 bytes)
WAT_ECHO_CVSS = """
(module
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (data (i32.const 1024) "{\\"level\\": \\"high\\", \\"score\\": 8.8, \\"label\\": \\"8.8 High\\"}")
  (func (export "kb_alloc") (param $len i32) (result i32)
    i32.const 2048
  )
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    (call $kb_output (i32.const 1024) (i32.const 52))
    i32.const 0
  )
)
"""

# 2. infinite_loop.wat -> infinite_loop.wasm
WAT_INFINITE_LOOP = """
(module
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (func (export "kb_alloc") (param $len i32) (result i32)
    i32.const 1024
  )
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    (loop $loop
      (br $loop)
    )
    i32.const 0
  )
)
"""

# 3. mem_grow_64mb.wat -> mem_grow_64mb.wasm
# Attempts to grow memory by 600 pages (37.5 MiB), exceeding the 32 MiB (512 pages) limit.
# If memory.grow returns -1, returns exit code 2 (signaling SCRIPT_MEMORY_LIMIT).
WAT_MEM_GROW_64MB = """
(module
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (func (export "kb_alloc") (param $len i32) (result i32)
    i32.const 1024
  )
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    (if (i32.eq (memory.grow (i32.const 600)) (i32.const -1))
      (then
        (return (i32.const 2))
      )
    )
    i32.const 0
  )
)
"""

# 4. wasi_fs_import.wat -> wasi_fs_import.wasm
# Declares forbidden import from wasi_snapshot_preview1
WAT_WASI_FS_IMPORT = """
(module
  (import "wasi_snapshot_preview1" "fd_read" (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (func (export "kb_alloc") (param $len i32) (result i32)
    i32.const 1024
  )
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    i32.const 0
  )
)
"""

# 5. require_qa_proof_link.wat -> require_qa_proof_link.wasm
# Pre-stores '{"allowed": true, "reason": "Verified QA link present"}' at offset 1024 (55 bytes)
WAT_REQUIRE_QA_PROOF_LINK = """
(module
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (data (i32.const 1024) "{\\"allowed\\": true, \\"reason\\": \\"Verified QA link present\\"}")
  (func (export "kb_alloc") (param $len i32) (result i32)
    i32.const 2048
  )
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    (call $kb_output (i32.const 1024) (i32.const 55))
    i32.const 0
  )
)
"""


def build_all() -> None:
    """Compile and write all 5 WebAssembly test fixtures."""
    fixtures = {
        "echo_cvss.wasm": WAT_ECHO_CVSS,
        "infinite_loop.wasm": WAT_INFINITE_LOOP,
        "mem_grow_64mb.wasm": WAT_MEM_GROW_64MB,
        "wasi_fs_import.wasm": WAT_WASI_FS_IMPORT,
        "require_qa_proof_link.wasm": WAT_REQUIRE_QA_PROOF_LINK,
    }
    for filename, wat in fixtures.items():
        out_path = FIXTURES_DIR / filename
        wasm_bytes = wasmtime.wat2wasm(wat)
        out_path.write_bytes(wasm_bytes)
        print(f"Compiled {filename} ({len(wasm_bytes)} bytes)")  # noqa: T201


if __name__ == "__main__":
    build_all()
