# bsm-test-utils

A robust test utility package designed to simulate Minecraft Bedrock Dedicated Server environments. It is primarily used for writing comprehensive integration tests (e.g., testing the Bedrock Server Manager) by providing programmatic fixtures, HTTP download mocking, and dynamic asset generation.

## Features

- **Dynamic Server Releases:** Generate zip files mimicking official Bedrock Server releases (custom versions, preview tags).
- **Dynamic Add-on Generation:** Programmatically build behavior packs, resource packs, and script packs. Generate them as directories or `.mcpack` zip files with optionally invalid configurations for edge-case testing.
- **Bundle Support:** Create `.mcaddon` (bundled packs) and `.mcworld` (worlds embedded with custom `level.dat` and packs).
- **Mock HTTP Server:** A lightweight, multithreaded `http.server` designed for testing download functionality directly in pytest, avoiding external network calls.
- **Pytest Fixtures:** Seamlessly integrated fixtures to use these tools out-of-the-box in your test suites.

## Installation

```bash
pip install bsm-test-utils
```

## Setup for Pytest

To use the built-in Pytest fixtures automatically in your tests, register them in your `conftest.py` file:

```python
# conftest.py
pytest_plugins = ["bsm_test_utils.fixtures"]
```

## Detailed Pytest Guide

The following examples demonstrate how to use `bsm-test-utils` to write powerful, isolated integration tests for Bedrock tooling.

### 1. Mocking a Server Download

Instead of hitting the real Minecraft download servers during your tests, use the `mock_http_server` and `dummy_server_zip` fixtures to generate a fake release and serve it locally.

```python
import urllib.request
import zipfile
from pathlib import Path

def test_download_and_extract_server(mock_http_server, dummy_server_zip, tmp_path):
    # 1. Generate the zip file directly into the mock server's directory
    # The factory returns the Path to the generated zip file.
    zip_path = dummy_server_zip(
        target_dir=mock_http_server.directory,
        version="1.20.10.01",
        is_preview=False
    )

    # 2. Construct the URL to the mock server
    download_url = f"{mock_http_server.url}/{zip_path.name}"

    # 3. Simulate your application's download logic
    dest_path = tmp_path / zip_path.name
    urllib.request.urlretrieve(download_url, dest_path)

    # 4. Verify the download and extract it
    assert dest_path.exists()

    extract_dir = tmp_path / "server"
    with zipfile.ZipFile(dest_path, "r") as zf:
        zf.extractall(extract_dir)

    # The dummy server contains standard config files and the platform binary
    assert (extract_dir / "server.properties").exists()
    assert (extract_dir / "behavior_packs").is_dir()
```

### 2. Testing Addon Management

You can inject pre-built valid or invalid addons to test how your application handles importing or reading them.

```python
import json

def test_addon_manifest_reading(valid_behavior_pack, invalid_behavior_pack):
    # valid_behavior_pack is a Path to an extracted directory
    with open(valid_behavior_pack / "manifest.json") as f:
        manifest = json.load(f)
    assert "uuid" in manifest["header"]
    assert manifest["modules"][0]["type"] == "data"

    # invalid_behavior_pack simulates a corrupt manifest (missing UUID)
    with open(invalid_behavior_pack / "manifest.json") as f:
        invalid_manifest = json.load(f)
    assert "uuid" not in invalid_manifest.get("header", {})
```

### 3. Working with Bundles (.mcaddon / .mcworld)

If your application supports `.mcaddon` or `.mcworld` file uploads, you can use the built-in fixtures that provide generated `.zip` files under those extensions.

```python
import zipfile

def test_mcaddon_extraction(valid_mcaddon_zip, tmp_path):
    # valid_mcaddon_zip is a Path to a .mcaddon file
    assert valid_mcaddon_zip.suffix == ".mcaddon"

    with zipfile.ZipFile(valid_mcaddon_zip, "r") as zf:
        # An .mcaddon usually contains multiple .mcpack files
        assert any(f.endswith(".mcpack") for f in zf.namelist())

def test_mcworld_import(valid_mcworld_zip, mock_http_server):
    # You can even move these bundles into the mock server for download testing
    import shutil
    dest = mock_http_server.directory / valid_mcworld_zip.name
    shutil.copy2(valid_mcworld_zip, dest)

    download_url = f"{mock_http_server.url}/{valid_mcworld_zip.name}"
    # ... assert your application handles the URL correctly
```

### 4. End-to-End Download Testing

For applications like `bedrock-server-manager` that scrape the official download endpoint, you can use the `mock_bedrock_api` fixture. It sets up a localized mock of `/api/v1.0/download/links` containing dynamically generated mock zips for stable and preview releases on both Linux and Windows.

```python
import json
import urllib.request

def test_bedrock_api_mock(mock_bedrock_api):
    # The fixture yields the mock_http_server instance, but with the API already populated
    api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"

    # 1. Fetch the JSON as your manager would
    req = urllib.request.Request(api_url)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())

    links = {item["downloadType"]: item["downloadUrl"] for item in data["result"]["links"]}

    # 2. Download a platform specific zip
    linux_url = links["serverBedrockLinux"]
    dest = mock_bedrock_api.directory / "downloaded.zip"
    urllib.request.urlretrieve(linux_url, dest)
    assert dest.exists()
```

### Reference: Available Pytest Fixtures

| Fixture Name | Return Type | Description |
| :--- | :--- | :--- |
| `mock_http_server` | `MockHTTPServer` | Yields a running multithreaded HTTP server bound to `127.0.0.1`. Automatically cleans up after the test. Access the URL via `.url` and its root directory via `.directory`. |
| `mock_bedrock_api` | `MockHTTPServer` | Yields a `mock_http_server` pre-populated with a mocked `/api/v1.0/download/links` endpoint serving generated server zips. |
| `dummy_server_zip` | `Callable` | A factory function: `def _factory(target_dir, version="...", is_preview=False, is_windows=None, filename=None)`. Returns a `Path` to the generated server zip. |
| `valid_behavior_pack` | `Path` | Path to a valid behavior pack directory. |
| `invalid_behavior_pack` | `Path` | Path to an invalid behavior pack directory (missing UUID). |
| `invalid_json_pack` | `Path` | Path to an invalid behavior pack directory with a fundamentally corrupt JSON manifest. |
| `valid_resource_pack` | `Path` | Path to a valid resource pack directory. |
| `valid_behavior_pack_zip` | `Path` | Path to a valid behavior pack `.mcpack` file. |
| `valid_mcaddon_zip` | `Path` | Path to a valid `.mcaddon` file (contains bundled behavior and resource packs). |
| `valid_mcworld_zip` | `Path` | Path to a valid `.mcworld` file (contains `level.dat` and embedded addons). |

### 5. Interacting with the Dummy Server

The generated server binaries in `bsm-test-utils` are more than just empty files. When executed, they print logs mimicking exactly what the official Bedrock dedicated server outputs.

You can also use special arguments and standard input commands to mock specific behaviors:

- **Immediate Crash**: Start the server with the `--mock-crash` argument to have it print a segfault message and immediately exit with code `1`.
- **Runtime Crash**: Send the string `__DUMMY__ CRASH` to the standard input while the server is running to simulate a random runtime panic (exits with code `1`).
- **Player Events**: Send `__DUMMY__ PLAYER_JOIN <username>` or `__DUMMY__ PLAYER_LEAVE <username>` to generate standard player connection/disconnection logs.
- **Graceful Shutdown**: Sending the standard Bedrock `stop` command will trigger a normal shutdown sequence resulting in an exit code `0`.

---

## Asset Generation (Manual Usage)

If you need even more customization, you can import and use the generation functions directly without fixtures:

```python
from bsm_test_utils import create_mcworld, create_behavior_pack, create_mcaddon

# 1. Create a behavior pack zip
create_behavior_pack("./packs", name="My BP", as_zip=True)

# 2. Create an mcaddon containing multiple custom packs
create_mcaddon(
    "./bundles",
    name="My Addon Bundle",
    packs=[
        {"name": "My Custom BP", "pack_type": "data"},
        {"name": "My Custom RP", "pack_type": "resources"}
    ]
)

# 3. Create a world with embedded addons
# This will also automatically generate world_behavior_packs.json
# and world_resource_packs.json mapping the generated packs.
create_mcworld(
    "./worlds",
    name="My World",
    level_dat_content="custom binary data",
    packs=[
        {"name": "Embedded BP", "pack_type": "data"},
        {"name": "Embedded RP", "pack_type": "resources"}
    ]
)
```
