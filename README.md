# bsm-test-utils

A reusable test toolkit designed to simulate Minecraft Bedrock Dedicated Server environments, realistic backup/restore datasets, and controlled failure scenarios. It is primarily used for writing comprehensive integration and performance tests (e.g., testing the Bedrock Server Manager) by providing programmatic fixtures, HTTP download mocking, synthetic dataset workloads, and dynamic asset generation.

## Features

- **Configurable Server Datasets & Backup Verification:** Generate reproducible server file trees (`DatasetSpec`, `create_server_dataset`) with tunable file counts, byte totals, size distributions, directory depth, and content profiles (`compressible`, `random`, `mixed`), paired with tree inventory diffing (`compare_trees`, `assert_trees_equal`), dataset mutations (`mutate_server_dataset`), and backup/restore benchmarking (`measure_backup_restore`).
- **Dynamic Server Releases & Setup:** Generate zip files (`create_server_zip`) or extracted directories (`setup_dummy_server`) mimicking official Bedrock Server releases for Windows and Linux (`amd64`).
- **Modular Add-on & Failure Generation:** Describe packs with `PackSpec` and `PackFaults`, build in-memory payloads once with `build_pack()`, and write directories (`write_pack_directory`), `.mcpack` (`write_mcpack`), `.mcaddon` (`create_mcaddon`), or `.mcworld` (`create_mcworld`), plus explicit corrupt/traversal/CRC-mismatch archive generators for negative testing.
- **Backup-Aware Go Dummy Server:** Supports `save hold`, `save query` (with configurable readiness polls and file lists), `save resume`, live file mutations during backup, startup/shutdown delays and failures, stdout/stderr bursts, partial lines, distinct player identities, and command recording.
- **Controllable Mock HTTP Server:** Multithreaded `MockHTTPServer` supporting static files, retry sequences, redirects, throttled/chunked downloads, truncated bodies, dropped connections, header overrides, and request recording.
- **Pytest Fixtures:** Out-of-the-box fixtures available via the `pytest` extra.

## Installation

```bash
pip install bsm-test-utils
# Or with pytest fixture dependencies:
pip install "bsm-test-utils[pytest]"
```

### Editable / Development Installs

Because the package bundles compiled Go executables (`bedrock_server` for Linux `amd64` and `bedrock_server.exe` for Windows `amd64`), build the Go binaries into `src/bsm_test_utils/data/` before running tests in an editable checkout:

```bash
cd src_go
GOOS=linux GOARCH=amd64 go build -o ../src/bsm_test_utils/data/bedrock_server main.go
GOOS=windows GOARCH=amd64 go build -o ../src/bsm_test_utils/data/bedrock_server.exe main.go
cd ..
pip install -e ".[dev]"
```

## Setup for Pytest

Register the built-in fixtures in your `conftest.py` file:

```python
# conftest.py
pytest_plugins = ["bsm_test_utils.fixtures"]
```

## Usage Guide

### 1. Configurable Server Datasets & Restore Verification

Generate realistic server trees and verify backup/restore integrity:

```python
from bsm_test_utils import (
    DatasetSpec,
    assert_trees_equal,
    create_server_dataset,
    measure_backup_restore,
    mutate_server_dataset,
)

dataset = create_server_dataset(
    target_dir="./server_data",
    spec=DatasetSpec(
        file_count=1_000,
        total_bytes=16 * 1024 * 1024,
        profile="mixed",
        seed=42,
    ),
)

# Mutate a deterministic subset of files between backups
mutation = mutate_server_dataset("./server_data", add_count=5, modify_count=5, delete_count=2, seed=99)

# Compare a restored directory against the source tree
assert_trees_equal("./server_data", "./restored_server_data")
```

> **Note:** Synthetic database files in `worlds/<level>/db/` include a header notice identifying them as test fixtures; they do not form a playable LevelDB world.

### 2. Modular Add-on, Bundle, and Negative Fixture Generation

```python
from bsm_test_utils import (
    PackFaults,
    PackSpec,
    build_pack,
    create_checksum_mismatch_archive,
    create_corrupt_archive,
    create_mcaddon,
    create_mcworld,
     create_traversal_archive,
    write_mcpack,
    write_pack_directory,
)

# Build a pack once and write it as both a directory and a .mcpack
spec = PackSpec(
    name="My Custom BP",
    pack_type="data",
    version=(1, 2, 0),
    min_engine_version=(1, 20, 0),
)
built = build_pack(spec)
write_pack_directory("./packs", built)
write_mcpack("./packs", built)

# Bundle packs into .mcaddon and .mcworld (accepts text or binary level.dat)
create_mcaddon("./bundles", name="My Addon Bundle", packs=[spec])
create_mcworld(
    "./worlds",
    name="My World",
    level_dat_content=b"\x08\x00\x00\x00binary-level-dat",
    packs=[spec],
)

# Explicit negative archive fixtures for import/restore error handling
create_corrupt_archive("./negative", filename="truncated.mcpack", mode="truncated_zip")
create_traversal_archive("./negative", filename="zipslip.zip", traversal_entry="../escaped.txt")
create_checksum_mismatch_archive("./negative", filename="bad_crc.zip")
```

### 3. Dummy Server Backup & Failure Scenarios

The compiled dummy server binary supports CLI flags and stdin commands for backup/recovery and process management tests:

- **CLI Flags:**
  - `--mock-crash`: Immediately log a segfault and exit.
  - `--startup-failure`: Fail during initialization before loading the world.
  - `--never-ready`: Start up without emitting `Server started.`.
  - `--startup-delay-ms=<int>`: Configure world/service startup delay (default `1000`).
  - `--stop-delay-ms=<int>` / `--ignore-stop`: Delay shutdown or ignore `stop` commands.
  - `--exit-code=<int>` / `--crash-exit-code=<int>`: Custom exit codes.
  - `--crash-after-ms=<int>`: Trigger a timed runtime crash.
  - `--save-ready-polls=<int>`: Number of `save query` calls required before emitting `Data saved. Files are now ready to be copied.` and the file list.
  - `--save-hold-fail`, `--save-query-fail`, `--save-resume-fail`: Simulate backup command failures.
  - `--save-mutate-file=<path>`: Modify a file during `save hold` / `save query` to simulate live world writes during backup.
  - `--command-log-file=<path>`: Record every received stdin command in order.
- **Stdin Commands:**
  - `save hold`, `save query`, `save resume`, `stop`
  - `__DUMMY__ CRASH [exit_code]` / `__DUMMY__ CRASH_AFTER <ms> [exit_code]`
  - `__DUMMY__ PLAYER_JOIN "<player name>" [xuid=...] [pfid=...]`
  - `__DUMMY__ PLAYER_LEAVE "<player name>" [xuid=...] [pfid=...]`
  - `__DUMMY__ STDOUT_BURST <lines> <bytes_per_line>` / `__DUMMY__ STDERR_BURST <lines> <bytes_per_line>`
  - `__DUMMY__ PARTIAL_LINE <text>` / `__DUMMY__ COMPLETE_LINE <text>`
  - `__DUMMY__ SET_SAVE_FAIL <hold|query|resume> <true|false>`
  - `__DUMMY__ SET_SAVE_POLLS <count>` / `__DUMMY__ SET_IGNORE_STOP <true|false>`
  - `__DUMMY__ DUMP_COMMANDS`

### 4. Controllable HTTP Download Mocking

```python
from bsm_test_utils import MockHTTPServer, RouteBehavior

with MockHTTPServer(directory="./served") as server:
    # Fail twice with 503, then succeed with 200
    server.add_retry_route("/release.zip", fail_statuses=[503, 503], final_status=200, body=b"zip-bytes")

    # Simulate a truncated download with mismatched Content-Length
    server.add_route(
        "/truncated.zip",
        RouteBehavior(body=b"0123456789" * 100, truncate_bytes=50, content_length_override=1000),
    )
```

### Reference: Available Pytest Fixtures

| Fixture Name | Return Type | Description |
| :--- | :--- | :--- |
| `mock_http_server` | `MockHTTPServer` | Yields a running multithreaded HTTP server bound to `127.0.0.1`. |
| `mock_bedrock_api` | `MockHTTPServer` | Yields a `mock_http_server` pre-populated with `/api/v1.0/download/links`. |
| `dummy_server_zip` | `Callable` | Factory returning a `Path` to a generated server zip. |
| `server_dataset_factory` | `Callable` | Factory returning a `DatasetResult` for a synthetic server dataset. |
| `valid_behavior_pack` | `Path` | Path to a valid behavior pack directory. |
| `invalid_behavior_pack` | `Path` | Path to an invalid behavior pack directory (missing UUID). |
| `invalid_json_pack` | `Path` | Path to a behavior pack directory with malformed JSON. |
| `valid_resource_pack` | `Path` | Path to a valid resource pack directory. |
| `valid_behavior_pack_zip` | `Path` | Path to a valid behavior pack `.mcpack` file. |
| `valid_mcaddon_zip` | `Path` | Path to a valid `.mcaddon` bundle. |
| `valid_mcworld_zip` | `Path` | Path to a valid `.mcworld` archive with embedded packs. |

## Process, download, and backup scenarios

Use the `dummy_server_install` pytest fixture for a writable copy of the host
dummy server. It sets `BSM_DUMMY_STARTUP_DELAY_MS=0` unless the environment
already provides a delay. Set the variable in a test or pass
`--startup-delay-ms` to exercise delayed readiness. The executable also
supports `--save-files-from-disk` or `BSM_DUMMY_SAVE_FILES_FROM_DISK=1` to
report actual world paths and byte counts when a manager issues `save query`
after `save hold`.

Use `DummyServerProcess` when the test owns the process. It drains both pipes
and captures recent stdout and stderr for timeout errors.

```python
from bsm_test_utils import DummyServerProcess

with DummyServerProcess(binary, cwd=server_dir) as server:
    server.wait_for_line("Server started.")
    server.send("__DUMMY__ PLAYER_JOIN Alex xuid=1234567890123456")
    server.wait_for_line("Player connected: Alex")
    server.send("stop")
    assert server.wait() == 0
```

When the manager owns the process, point `BSM_DUMMY_SCENARIO` or `--scenario`
at a JSON file. Steps run once, in file order for each trigger. A
`ready` step runs after startup output. An `after_command` step runs
after the matching stdin command completes.

```json
[
  {"when": "ready", "actions": ["__DUMMY__ PLAYER_JOIN Alex"]},
  {
    "when": "after_command",
    "command": "save hold",
    "actions": ["__DUMMY__ STDERR_BURST 1 16"]
  }
]
```

The `bedrock_download_catalog` fixture can publish successive versions with
`publish(stable="1.2.3", preview="1.2.4")`. Managers can re-fetch the links
endpoint while existing download URLs continue to serve their original
archives. Catalog fixtures cache one ZIP per target OS per pytest worker.
To test conditional or resumable downloads, configure a route with
`RouteBehavior(file_path=archive, accept_ranges=True, etag='"version-1"')`.

Use `measure_async_backup_restore` for awaitable backup and restore callbacks.
It returns the same summary as `measure_backup_restore`. To generate large
repeatable datasets quickly, use `DatasetSpec(profile="seeded-random")`.
