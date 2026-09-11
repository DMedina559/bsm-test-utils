import tempfile
from pathlib import Path

import pytest

from .addons import (create_behavior_pack, create_mcaddon, create_mcworld,
                     create_resource_pack)
from .dummy_server import create_server_zip
from .http_mock import MockHTTPServer


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
