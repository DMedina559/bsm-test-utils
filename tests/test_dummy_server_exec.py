import subprocess
import sys
from pathlib import Path


def test_dummy_server_logs_and_crash():
    """
    Tests that the compiled Go dummy server outputs the expected logs
    and handles the --mock-crash flag correctly.
    """
    # Locate the built binary
    package_dir = Path(__file__).parent.parent / "src" / "bsm_test_utils"
    data_dir = package_dir / "data"

    import platform

    binary_name = (
        "bedrock_server.exe" if platform.system() == "Windows" else "bedrock_server"
    )
    binary_path = data_dir / binary_name

    if not binary_path.exists():
        import pytest

        pytest.skip(f"Binary {binary_name} not built, skipping executable test.")

    # 1. Test standard startup logs
    # We pass 'stop' to stdin to make it shut down gracefully
    process = subprocess.Popen(
        [str(binary_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, _ = process.communicate(input="stop\n", timeout=5)

    # Check for specific log lines matching Bedrock format
    assert "NO LOG FILE! - setting up server logging..." in stdout
    assert "Starting Server" in stdout
    assert "Version: " in stdout
    assert "IPv4 supported, port: 19132" in stdout
    assert "Server started." in stdout
    assert "Server stop requested." in stdout
    assert "Quit correctly" in stdout

    assert process.returncode == 0

    # 2. Test crash simulation
    process_crash = subprocess.Popen(
        [str(binary_path), "--mock-crash"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_crash, _ = process_crash.communicate(timeout=2)
    assert "CRASH: Segfault simulating server failure" in stdout_crash
    assert process_crash.returncode == 1

    # 3. Test runtime crash
    process_runtime_crash = subprocess.Popen(
        [str(binary_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_rt_crash, _ = process_runtime_crash.communicate(
        input="__DUMMY__ CRASH\n", timeout=5
    )
    assert "CRASH: Fatal runtime error encountered" in stdout_rt_crash
    assert process_runtime_crash.returncode == 1
