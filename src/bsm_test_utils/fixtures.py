import tempfile
from pathlib import Path

import pytest

from .addons import (create_behavior_pack, create_mcaddon, create_mcworld,
                     create_resource_pack)
import json
from .dummy_server import create_server_zip
from .http_mock import MockHTTPServer


@pytest.fixture
def mock_bedrock_api(mock_http_server, dummy_server_zip):
    """
    Sets up a mock Bedrock download API on the mock HTTP server.
    It serves standard and preview dummy server zips for Windows and Linux,
    and provides the download/links endpoint pointing to these local zips.
    
    Usage:
    def test_downloader(mock_bedrock_api):
        # mock_bedrock_api is the mock_http_server instance
        api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"
        # BSM downloader will fetch links from here and download local zips
    """
    api_dir = mock_http_server.directory / "api" / "v1.0" / "download"
    api_dir.mkdir(parents=True, exist_ok=True)
    
    base_url = mock_http_server.url
    versions = {
        "stable": "1.26.45.1",
        "preview": "1.26.60.23"
    }

    # Helper to create a zip and return its mapped URL
    def _create_and_map(target_subpath: str, version: str, is_preview: bool, is_windows: bool, filename: str) -> str:
        target_dir = mock_http_server.directory / target_subpath
        target_dir.mkdir(parents=True, exist_ok=True)
        dummy_server_zip(
            target_dir=target_dir,
            version=version,
            is_preview=is_preview,
            is_windows=is_windows,
            filename=filename
        )
        return f"{base_url}/{target_subpath}/{filename}"
        
    win_stable = _create_and_map(
        "bedrockdedicatedserver/bin-win", 
        versions["stable"], False, True, 
        f"bedrock-server-{versions['stable']}.zip"
    )
    linux_stable = _create_and_map(
        "bedrockdedicatedserver/bin-linux", 
        versions["stable"], False, False, 
        f"bedrock-server-{versions['stable']}.zip"
    )
    win_preview = _create_and_map(
        "bedrockdedicatedserver/bin-win-preview", 
        versions["preview"], True, True, 
        f"bedrock-server-{versions['preview']}.zip"
    )
    linux_preview = _create_and_map(
        "bedrockdedicatedserver/bin-linux-preview", 
        versions["preview"], True, False, 
        f"bedrock-server-{versions['preview']}.zip"
    )

    links_data = {
        "result": {
            "links": [
                {"downloadType": "serverBedrockWindows", "downloadUrl": win_stable},
                {"downloadType": "serverBedrockLinux", "downloadUrl": linux_stable},
                {"downloadType": "serverBedrockPreviewWindows", "downloadUrl": win_preview},
                {"downloadType": "serverBedrockPreviewLinux", "downloadUrl": linux_preview},
                {"downloadType": "serverJar", "downloadUrl": f"{base_url}/server.jar"} # dummy jar
            ]
        }
    }
    
    with open(api_dir / "links", "w") as f:
        json.dump(links_data, f)
        
    return mock_http_server


@pytest.fixture
def mock_http_server():
    """
    Yields a running MockHTTPServer instance serving a temporary directory.
    Useful for mocking downloads of server zips or addons.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        server = MockHTTPServer(directory=tmpdir)
        server.start()
        yield server
        server.stop()

@pytest.fixture
def dummy_server_zip(tmp_path):
    """
    Provides a factory function to generate a dummy server zip file.
    
    Usage:
    def test_something(dummy_server_zip):
        zip_path = dummy_server_zip(version="1.20.10.01", is_preview=False)
    """
    def _factory(**kwargs):
        if "target_dir" not in kwargs:
            kwargs["target_dir"] = tmp_path
        return create_server_zip(**kwargs)
    return _factory

@pytest.fixture
def valid_behavior_pack(tmp_path):
    """Provides a path to a valid behavior pack directory."""
    return create_behavior_pack(tmp_path, name="Valid BP", valid=True)

@pytest.fixture
def valid_resource_pack(tmp_path):
    """Provides a path to a valid resource pack directory."""
    return create_resource_pack(tmp_path, name="Valid RP", valid=True)

@pytest.fixture
def invalid_behavior_pack(tmp_path):
    """Provides a path to an invalid behavior pack directory (missing UUID)."""
    return create_behavior_pack(tmp_path, name="Invalid BP", valid=False)

@pytest.fixture
def valid_behavior_pack_zip(tmp_path):
    """Provides a path to a valid behavior pack .mcpack file."""
    return create_behavior_pack(tmp_path, name="Valid BP Zip", valid=True, as_zip=True)

@pytest.fixture
def valid_mcaddon_zip(tmp_path):
    """Provides a path to a valid .mcaddon file containing a behavior and resource pack."""
    return create_mcaddon(tmp_path, name="Valid Bundle")

@pytest.fixture
def valid_mcworld_zip(tmp_path):
    """Provides a path to a valid .mcworld file with embedded addons."""
    packs = [
        {"name": "World BP", "pack_type": "data"},
        {"name": "World RP", "pack_type": "resources"}
    ]
    return create_mcworld(tmp_path, name="Valid World", packs=packs)
