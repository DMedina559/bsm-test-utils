import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pytest

from .addons import (
    PackSpec,
    create_behavior_pack,
    create_mcaddon,
    create_mcworld,
    create_resource_pack,
)
from .datasets import DatasetResult, DatasetSpec, create_server_dataset
from .dummy_server import create_server_zip, setup_dummy_server
from .http_mock import BedrockDownloadCatalog, MockHTTPServer


@pytest.fixture(scope="session")
def bedrock_download_archives(tmp_path_factory):
    """Build one immutable release ZIP per OS per pytest worker."""
    directory = tmp_path_factory.mktemp("bedrock-downloads")
    return {
        target: create_server_zip(
            directory,
            is_windows=target == "windows",
            machine="amd64",
            filename=f"{target}.zip",
        )
        for target in ("windows", "linux")
    }


@pytest.fixture
def bedrock_download_catalog(mock_http_server, bedrock_download_archives):
    return BedrockDownloadCatalog(mock_http_server, bedrock_download_archives)


@pytest.fixture
def mock_bedrock_api(bedrock_download_catalog):
    """Serve the default stable and preview download catalog."""
    return bedrock_download_catalog.publish()


@pytest.fixture(scope="session")
def dummy_server_template(tmp_path_factory):
    """Install the host dummy once for tests that do not exercise ZIP extraction."""
    return setup_dummy_server(tmp_path_factory.mktemp("dummy-bedrock-template"))


@pytest.fixture
def dummy_server_install(dummy_server_template, tmp_path, monkeypatch):
    """Copy the dummy installation and default manager-launched processes to fast startup."""
    monkeypatch.setenv(
        "BSM_DUMMY_STARTUP_DELAY_MS", os.environ.get("BSM_DUMMY_STARTUP_DELAY_MS", "0")
    )
    return shutil.copytree(dummy_server_template, tmp_path / "dummy-bedrock")


@pytest.fixture
def mock_http_server():
    """
    Yields a running MockHTTPServer instance serving a temporary directory.
    Useful for mocking downloads of server zips or addons.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with MockHTTPServer(directory=tmpdir) as server:
            yield server


@pytest.fixture
def dummy_server_zip(tmp_path):
    """
    Provides a factory function to generate a dummy server zip file.
    """

    def _factory(**kwargs):
        if "target_dir" not in kwargs:
            kwargs["target_dir"] = tmp_path
        return create_server_zip(**kwargs)

    return _factory


@pytest.fixture
def server_dataset_factory(tmp_path):
    """
    Provides a factory function to generate a synthetic server dataset.
    """

    def _factory(
        target_dir: Optional[Path] = None,
        spec: Optional[DatasetSpec] = None,
        **overrides,
    ) -> DatasetResult:
        dest = target_dir if target_dir is not None else tmp_path / "dataset"
        if spec is not None and overrides:
            raise TypeError("Pass either a dataset spec or keyword overrides")
        effective_spec = spec if spec is not None else DatasetSpec(**overrides)
        return create_server_dataset(dest, spec=effective_spec)

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
def invalid_json_pack(tmp_path):
    """Provides a path to a behavior pack directory with a broken JSON manifest."""
    return create_behavior_pack(tmp_path, name="Invalid JSON BP", invalid_json=True)


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
        PackSpec(name="World BP", pack_type="data"),
        PackSpec(name="World RP", pack_type="resources"),
    ]
    return create_mcworld(tmp_path, name="Valid World", packs=packs)
