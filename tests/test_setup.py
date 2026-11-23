import platform
import tempfile
from pathlib import Path

from bsm_test_utils import run_server_process, setup_dummy_server


def test_setup_dummy_server():
    is_windows = platform.system() == "Windows"
    binary_name = "bedrock_server.exe" if is_windows else "bedrock_server"

    with tempfile.TemporaryDirectory() as temp_dir:
        setup_dummy_server(temp_dir)

        target = Path(temp_dir)

        assert (target / binary_name).exists()
        assert (target / "server.properties").exists()
        assert (target / "allowlist.json").exists()
        assert (target / "permissions.json").exists()
        assert (target / "behavior_packs").is_dir()
        assert (target / "resource_packs").is_dir()
        assert (target / "worlds" / "Bedrock level" / "db").is_dir()

        returncode, stdout, _ = run_server_process(
            target / binary_name,
            args=["--startup-delay-ms=10"],
            stdin_text="stop\n",
            timeout=5.0,
        )
        assert "Server stop requested." in stdout
        assert "Quit correctly" in stdout
        assert returncode == 0
