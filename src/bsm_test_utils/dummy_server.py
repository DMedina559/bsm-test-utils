import os
import platform
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from .addons import validate_child_path

REQUIRED_CONFIG_FILES: Tuple[str, ...] = (
    "server.properties",
    "allowlist.json",
    "permissions.json",
)
STANDARD_SERVER_DIRECTORIES: Tuple[str, ...] = (
    "behavior_packs",
    "resource_packs",
    "worlds/Bedrock level/db",
)

SUPPORTED_ARCHITECTURES = {
    "x86_64": "amd64",
    "amd64": "amd64",
}


def get_package_data_dir() -> Path:
    """Returns the path to the packaged data directory."""
    return Path(__file__).parent / "data"


def resolve_platform_spec(
    is_windows: Optional[bool] = None,
    system: Optional[str] = None,
    machine: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Resolves and validates the target OS, normalized architecture, and binary filename.
    Supported targets are Windows amd64 and Linux amd64.
    """
    if is_windows is not None:
        norm_os = "windows" if is_windows else "linux"
    else:
        raw_sys = (system or platform.system()).strip().lower()
        if raw_sys == "windows":
            norm_os = "windows"
        elif raw_sys == "linux":
            norm_os = "linux"
        else:
            raise RuntimeError(
                f"Unsupported operating system {system or platform.system()!r}. "
                "Bedrock Dedicated Server dummy binaries only support Windows and Linux."
            )

    raw_arch = (machine or platform.machine() or "amd64").strip().lower()
    norm_arch = SUPPORTED_ARCHITECTURES.get(raw_arch)
    if norm_arch is None:
        raise RuntimeError(
            f"Unsupported architecture {machine or platform.machine()!r}. "
            "Only amd64 / x86_64 is supported."
        )

    binary_name = "bedrock_server.exe" if norm_os == "windows" else "bedrock_server"
    return norm_os, norm_arch, binary_name


def resolve_server_binary(
    is_windows: Optional[bool] = None,
    system: Optional[str] = None,
    machine: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Tuple[Path, str, bool]:
    """
    Locates the compiled dummy server binary for the requested OS/architecture.
    Raises FileNotFoundError if the platform binary does not exist.
    """
    norm_os, _, binary_name = resolve_platform_spec(
        is_windows=is_windows, system=system, machine=machine
    )
    target_is_windows = norm_os == "windows"
    pkg_data = data_dir or get_package_data_dir()

    candidate = pkg_data / binary_name
    if candidate.exists():
        return candidate, binary_name, target_is_windows

    # Fallback to src_go only if the OS-specific binary name exists there
    src_go_dir = Path(__file__).parent.parent.parent / "src_go"
    os_specific_go = src_go_dir / binary_name
    if os_specific_go.exists():
        return os_specific_go, binary_name, target_is_windows

    # Legacy src_go/dummy_server (or dummy_server.exe) only if it matches the requested OS
    legacy_name = "dummy_server.exe" if target_is_windows else "dummy_server"
    legacy_go = src_go_dir / legacy_name
    if legacy_go.exists():
        return legacy_go, binary_name, target_is_windows

    raise FileNotFoundError(
        f"Could not find {binary_name} for {norm_os}/amd64 in {pkg_data}. "
        "Ensure Go binaries are built into src/bsm_test_utils/data/ before running."
    )


def validate_required_assets(data_dir: Optional[Path] = None) -> Path:
    """
    Verifies that all required server configuration files exist in the package data dir.
    """
    pkg_data = data_dir or get_package_data_dir()
    missing = [cfg for cfg in REQUIRED_CONFIG_FILES if not (pkg_data / cfg).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing required server configuration asset(s) in {pkg_data}: {', '.join(missing)}"
        )
    return pkg_data


def setup_dummy_server(
    target_dir: Union[str, Path],
    is_windows: Optional[bool] = None,
    *,
    system: Optional[str] = None,
    machine: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Path:
    """
    Sets up a dummy Bedrock server environment in the specified target directory.
    Copies the appropriate executable for the target OS/architecture and populates
    default configuration files, behavior_packs, resource_packs, and world directories.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    pkg_data = validate_required_assets(data_dir)
    src_binary, binary_name, target_is_windows = resolve_server_binary(
        is_windows=is_windows, system=system, machine=machine, data_dir=pkg_data
    )

    dest_binary = target / binary_name
    shutil.copy2(src_binary, dest_binary)
    if not target_is_windows:
        os.chmod(dest_binary, 0o755)

    for config in REQUIRED_CONFIG_FILES:
        shutil.copy2(pkg_data / config, target / config)

    for rel_dir in STANDARD_SERVER_DIRECTORIES:
        (target / rel_dir).mkdir(parents=True, exist_ok=True)

    return target


def create_server_zip(
    target_dir: Union[str, Path],
    version: str = "1.20.0.01",
    is_preview: bool = False,
    is_windows: Optional[bool] = None,
    filename: Optional[str] = None,
    *,
    system: Optional[str] = None,
    machine: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Path:
    """
    Creates a mock bedrock server zip release.
    Packages the Go dummy server binary along with default server properties
    and configuration files into a zip archive matching the standard release format.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if filename:
        zip_name = filename
    else:
        if "/" in version or "\\" in version or ".." in version:
            raise ValueError(f"Unsafe version string for filename: {version!r}")
        zip_name = f"bedrock-server-{version}.zip"

    zip_path = validate_child_path(target, zip_name)

    pkg_data = validate_required_assets(data_dir)
    src_binary, binary_name, _ = resolve_server_binary(
        is_windows=is_windows, system=system, machine=machine, data_dir=pkg_data
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_binary, arcname=binary_name)

        for config in REQUIRED_CONFIG_FILES:
            zf.write(pkg_data / config, arcname=config)

        for rel_dir in STANDARD_SERVER_DIRECTORIES:
            arc_dir = rel_dir.rstrip("/") + "/"
            zf.writestr(arc_dir, "")

    return zip_path


def run_server_process(
    binary_path: Union[str, Path],
    args: Optional[Sequence[str]] = None,
    stdin_text: Optional[str] = None,
    timeout: float = 5.0,
    cwd: Optional[Union[str, Path]] = None,
) -> Tuple[int, str, str]:
    """
    Starts the dummy server executable, communicates with a timeout,
    and guarantees process termination and reaping in a finally block.
    """
    cmd = [str(binary_path)] + list(args or [])
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )
    try:
        stdout, stderr = proc.communicate(input=stdin_text, timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
