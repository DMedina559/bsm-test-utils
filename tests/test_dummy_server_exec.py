import subprocess
from pathlib import Path

import pytest

from bsm_test_utils.dummy_server import resolve_server_binary, run_server_process


def _get_host_binary() -> Path:
    try:
        binary_path, _, _ = resolve_server_binary()
    except (FileNotFoundError, RuntimeError) as exc:
        pytest.skip(f"Host dummy server binary unavailable: {exc}")
    if not binary_path.exists():
        pytest.skip(f"Binary {binary_path} not built, skipping executable test.")
    return binary_path


def test_dummy_server_logs_and_crash():
    """
    Tests that the compiled Go dummy server outputs the expected logs
    and handles --mock-crash and runtime crashes correctly.
    """
    binary_path = _get_host_binary()

    # 1. Standard startup logs + graceful stop
    rc, stdout, _ = run_server_process(
        binary_path,
        args=["--startup-delay-ms=10"],
        stdin_text="stop\n",
        timeout=5.0,
    )
    assert "NO LOG FILE! - setting up server logging..." in stdout
    assert "Starting Server" in stdout
    assert "Version: " in stdout
    assert "IPv4 supported, port: 19132" in stdout
    assert "Server started." in stdout
    assert "Server stop requested." in stdout
    assert "Quit correctly" in stdout
    assert rc == 0

    # 2. Immediate crash simulation with custom exit code
    rc_crash, stdout_crash, _ = run_server_process(
        binary_path,
        args=["--mock-crash", "--crash-exit-code=137"],
        timeout=3.0,
    )
    assert "CRASH: Segfault simulating server failure" in stdout_crash
    assert rc_crash == 137

    # 3. Runtime crash via stdin
    rc_rt, stdout_rt, _ = run_server_process(
        binary_path,
        args=["--startup-delay-ms=10"],
        stdin_text="__DUMMY__ CRASH 99\n",
        timeout=5.0,
    )
    assert "CRASH: Fatal runtime error encountered" in stdout_rt
    assert rc_rt == 99


def test_dummy_server_save_hold_query_resume_and_recovery(tmp_path):
    binary_path = _get_host_binary()
    cmd_log = tmp_path / "commands.log"
    mutated_file = tmp_path / "worlds" / "Bedrock level" / "db" / "live.ldb"

    commands = "\n".join(
        [
            "save hold",
            "save query",
            "save query",
            "save resume",
            "__DUMMY__ SET_SAVE_FAIL query true",
            "save hold",
            "save query",
            "save resume",
            "__DUMMY__ DUMP_COMMANDS",
            "stop",
        ]
    )

    rc, stdout, _ = run_server_process(
        binary_path,
        args=[
            "--startup-delay-ms=5",
            "--save-ready-polls=2",
            f"--command-log-file={cmd_log}",
            f"--save-mutate-file={mutated_file}",
        ],
        stdin_text=commands + "\n",
        timeout=5.0,
    )
    assert rc == 0
    assert "Saving..." in stdout
    assert "The save is in progress..." in stdout
    assert "Data saved. Files are now ready to be copied." in stdout
    assert "Bedrock level/db/000003.ldb:1240" in stdout
    assert "Save query failed: backup state error." in stdout
    assert stdout.count("Changes to the level are resumed.") == 2
    assert mutated_file.exists()

    recorded = cmd_log.read_text(encoding="utf-8").strip().splitlines()
    assert recorded[:4] == ["save hold", "save query", "save query", "save resume"]
    assert recorded[-1] == "stop"


def test_dummy_server_players_bursts_and_timeout_cleanup():
    binary_path = _get_host_binary()

    commands = "\n".join(
        [
            '__DUMMY__ PLAYER_JOIN "Steve The Builder"',
            '__DUMMY__ PLAYER_JOIN "Alex The Explorer"',
            '__DUMMY__ PLAYER_LEAVE "Steve The Builder"',
            "__DUMMY__ STDOUT_BURST 10 32",
            "__DUMMY__ STDERR_BURST 5 16",
            "__DUMMY__ PARTIAL_LINE partial_chunk_",
            "__DUMMY__ COMPLETE_LINE end_of_line",
            "stop",
        ]
    )
    rc, stdout, stderr = run_server_process(
        binary_path,
        args=["--startup-delay-ms=5"],
        stdin_text=commands + "\n",
        timeout=5.0,
    )
    assert rc == 0
    assert "Player connected: Steve The Builder, xuid:" in stdout
    assert "Player connected: Alex The Explorer, xuid:" in stdout
    assert "Player disconnected: Steve The Builder, xuid:" in stdout
    assert "BURST 00009" in stdout
    assert "partial_chunk_end_of_line" in stdout
    assert "[STDERR BURST 00004]" in stderr

    # Verify timeout cleanup kills and reaps a server that ignores stop
    with pytest.raises(subprocess.TimeoutExpired):
        run_server_process(
            binary_path,
            args=["--startup-delay-ms=5", "--ignore-stop"],
            stdin_text="stop\n",
            timeout=0.3,
        )


def test_interactive_disk_save_scenario(tmp_path):
    import json

    from bsm_test_utils import DummyServerProcess, setup_dummy_server

    install = setup_dummy_server(tmp_path / "install")
    binary = install / _get_host_binary().name
    world_file = install / "worlds/Bedrock level/db/000003.ldb"
    world_file.write_bytes(b"world")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            [
                {"when": "ready", "actions": ["__DUMMY__ PLAYER_JOIN Alex"]},
                {
                    "when": "after_command",
                    "command": "save hold",
                    "actions": ["__DUMMY__ STDERR_BURST 1 16"],
                },
            ]
        ),
        encoding="utf-8",
    )

    with DummyServerProcess(
        binary,
        ["--save-files-from-disk"],
        cwd=install,
        env={"BSM_DUMMY_SCENARIO": str(scenario)},
    ) as process:
        process.wait_for_line("Server started.")
        process.wait_for_line("Player connected: Alex, xuid:")
        process.send("save hold")
        process.wait_for_line("STDERR BURST", stream="stderr")
        process.send("save query")
        process.wait_for_line("Bedrock level/db/000003.ldb:5")
        process.send("save resume")
        process.wait_for_line("Changes to the level are resumed.")
        process.send("stop")
        assert process.wait() == 0
    binary.unlink()
