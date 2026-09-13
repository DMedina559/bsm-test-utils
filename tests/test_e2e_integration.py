import urllib.request
import zipfile
from pathlib import Path


def test_full_integration_flow(
    mock_http_server, dummy_server_zip, valid_behavior_pack_zip
):
    """
    Simulates a full integration test flow:
    1. Generate a dummy server zip and a valid addon.
    2. Host them on the mock HTTP server.
    3. Download them and extract them.
    4. Assert everything is exactly where it should be.
    """
    # 1. Generate assets directly in the mock server's directory
    server_zip_path = dummy_server_zip(
        target_dir=mock_http_server.directory, version="1.20.10.01"
    )

    import shutil

    # Copy the generated valid_behavior_pack_zip into the server directory
    dest_addon_path = mock_http_server.directory / valid_behavior_pack_zip.name
    shutil.copy2(valid_behavior_pack_zip, dest_addon_path)

    # 2. Download them using the mock server URL
    download_dir = Path(mock_http_server.directory) / "downloads"
    download_dir.mkdir()

    downloaded_zip = download_dir / server_zip_path.name
    urllib.request.urlretrieve(
        f"{mock_http_server.url}/{server_zip_path.name}", downloaded_zip
    )

    downloaded_addon = download_dir / dest_addon_path.name
    urllib.request.urlretrieve(
        f"{mock_http_server.url}/{dest_addon_path.name}", downloaded_addon
    )

    assert downloaded_zip.exists()
    assert downloaded_addon.exists()

    # 3. Extract the downloaded server
    extract_dir = download_dir / "server_extracted"
    with zipfile.ZipFile(downloaded_zip, "r") as zf:
        zf.extractall(extract_dir)

    # 4. Asserts
    # E2E runs natively, so test expects the current OS binary
    import platform

    binary_name = (
        "bedrock_server.exe" if platform.system() == "Windows" else "bedrock_server"
    )
    assert (extract_dir / binary_name).exists()
    assert (extract_dir / "server.properties").exists()
    assert (extract_dir / "behavior_packs").is_dir()
