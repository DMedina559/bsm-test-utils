import platform
import subprocess
import tempfile
from pathlib import Path

from bsm_test_utils import setup_dummy_server


def test_setup_dummy_server():
    is_windows = platform.system() == "Windows"
    binary_name = "bedrock_server.exe" if is_windows else "bedrock_server"
    
    package_data_dir = Path(__file__).parent.parent / "src" / "bsm_test_utils" / "data"
    dest_binary = package_data_dir / binary_name

    # Check if the binary was built successfully by your build command
    if not dest_binary.exists():
        raise FileNotFoundError(f"Could not find built binary at {dest_binary}. Did you run the go build command?")

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