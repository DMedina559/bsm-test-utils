import os
import platform
import subprocess
import tempfile
from pathlib import Path

from bsm_test_utils import setup_dummy_server


def test_setup_dummy_server():
    # First, mock the binary existence by copying the built dummy_server into data
    binary_name = (
        "bedrock_server.exe" if platform.system() == "Windows" else "bedrock_server"
    )
    package_data_dir = Path(__file__).parent.parent / "src" / "bsm_test_utils" / "data"

    # Copy from src_go to data for testing
    built_binary = Path(__file__).parent.parent / "src_go" / "dummy_server"
    dest_binary = package_data_dir / binary_name

    import shutil

    shutil.copy2(built_binary, dest_binary)

    with tempfile.TemporaryDirectory() as temp_dir:
        setup_dummy_server(temp_dir)

        target = Path(temp_dir)

        assert (target / binary_name).exists()
        assert (target / "server.properties").exists()
        assert (target / "allowlist.json").exists()
        assert (target / "permissions.json").exists()
        assert (target / "behavior_packs").is_dir()
        assert (target / "worlds" / "Bedrock level" / "db").is_dir()

        # Test executing the binary
        proc = subprocess.Popen(
            [str(target / binary_name)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        stdout, _ = proc.communicate(input="stop\n", timeout=5)
        assert "Server stop requested." in stdout
        assert "Quit correctly" in stdout
        assert proc.returncode == 0
