import platform
import zipfile

from bsm_test_utils.dummy_server import create_server_zip


def test_create_server_zip_default(tmp_path):
    zip_path = create_server_zip(tmp_path, version="1.20.10.01")
    assert zip_path.exists()
    
    os_name = "win" if platform.system() == "Windows" else "ubuntu"
    assert zip_path.name == f"bedrock-server-1.20.10.01-{os_name}.zip"
    
    binary_name = "bedrock_server.exe" if platform.system() == "Windows" else "bedrock_server"
    
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert binary_name in namelist
        assert "server.properties" in namelist
        assert "behavior_packs/" in namelist

def test_create_server_zip_preview(tmp_path):
    zip_path = create_server_zip(tmp_path, version="1.20.20.21", is_preview=True)
    assert zip_path.exists()
    os_name = "win" if platform.system() == "Windows" else "ubuntu"
    assert zip_path.name == f"bedrock-server-1.20.20.21-preview-{os_name}.zip"
