import platform
import zipfile

import pytest

from bsm_test_utils.dummy_server import (
    create_server_zip,
    resolve_platform_spec,
    resolve_server_binary,
    setup_dummy_server,
)


def test_create_server_zip_default(tmp_path):
    zip_path = create_server_zip(tmp_path, version="1.20.10.01")
    assert zip_path.exists()
    assert zip_path.name == "bedrock-server-1.20.10.01.zip"

    binary_name = (
        "bedrock_server.exe" if platform.system() == "Windows" else "bedrock_server"
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert binary_name in namelist
        assert "server.properties" in namelist
        assert "allowlist.json" in namelist
        assert "permissions.json" in namelist
        assert "behavior_packs/" in namelist
        assert "resource_packs/" in namelist
        assert "worlds/Bedrock level/db/" in namelist


def test_create_server_zip_preview(tmp_path):
    zip_path = create_server_zip(tmp_path, version="1.20.20.21", is_preview=True)
    assert zip_path.exists()
    assert zip_path.name == "bedrock-server-1.20.20.21.zip"


def test_binary_resolution_by_os_and_arch(tmp_path):
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    for cfg in ("server.properties", "allowlist.json", "permissions.json"):
        (fake_data / cfg).write_text("{}", encoding="utf-8")

    (fake_data / "bedrock_server").write_bytes(b"\x7fELF_LINUX_BINARY")
    (fake_data / "bedrock_server.exe").write_bytes(b"MZ_WINDOWS_BINARY")

    win_bin, win_name, is_win = resolve_server_binary(
        is_windows=True, data_dir=fake_data
    )
    assert is_win is True
    assert win_name == "bedrock_server.exe"
    assert win_bin.read_bytes() == b"MZ_WINDOWS_BINARY"

    lin_bin, lin_name, is_win_lin = resolve_server_binary(
        is_windows=False, data_dir=fake_data
    )
    assert is_win_lin is False
    assert lin_name == "bedrock_server"
    assert lin_bin.read_bytes() == b"\x7fELF_LINUX_BINARY"

    # Verify cross-packaging into ZIP uses the requested OS binary
    win_zip = create_server_zip(
        tmp_path / "out_win", is_windows=True, data_dir=fake_data
    )
    with zipfile.ZipFile(win_zip, "r") as zf:
        assert zf.read("bedrock_server.exe") == b"MZ_WINDOWS_BINARY"

    lin_zip = create_server_zip(
        tmp_path / "out_lin", is_windows=False, data_dir=fake_data
    )
    with zipfile.ZipFile(lin_zip, "r") as zf:
        assert zf.read("bedrock_server") == b"\x7fELF_LINUX_BINARY"


def test_unsupported_platform_and_missing_assets(tmp_path):
    with pytest.raises(RuntimeError, match="Unsupported operating system"):
        resolve_platform_spec(system="Darwin", machine="x86_64")

    with pytest.raises(RuntimeError, match="Unsupported architecture"):
        resolve_platform_spec(system="Linux", machine="arm64")

    empty_data = tmp_path / "empty_data"
    empty_data.mkdir()
    with pytest.raises(
        FileNotFoundError, match="Missing required server configuration"
    ):
        setup_dummy_server(tmp_path / "server", data_dir=empty_data)
