import os
import shutil
import platform
from pathlib import Path

def setup_dummy_server(target_dir: str):
    """
    Sets up a dummy Bedrock server environment in the specified target directory.
    This includes copying the appropriate executable for the current OS platform
    and populating dummy configuration files, worlds, and behavior packs.

    :param target_dir: The directory where the dummy server will be set up.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    
    # 1. Determine platform and copy the correct binary
    package_data_dir = Path(__file__).parent / "data"
    is_windows = platform.system() == "Windows"
    binary_name = "bedrock_server.exe" if is_windows else "bedrock_server"
    
    src_binary = package_data_dir / binary_name
    dest_binary = target / binary_name
    
    if not src_binary.exists():
        raise FileNotFoundError(
            f"Could not find {binary_name} in the package data. Make sure "
            "the package was built correctly with the Go binaries included."
        )
    
    shutil.copy2(src_binary, dest_binary)
    if not is_windows:
        # Ensure the binary is executable on Linux/macOS
        os.chmod(dest_binary, 0o755)
        
    # 2. Copy configuration files
    configs = ["server.properties", "allowlist.json", "permissions.json"]
    for config in configs:
        src_config = package_data_dir / config
        if src_config.exists():
            shutil.copy2(src_config, target / config)
            
    # 3. Create dummy directories required by validation
    (target / "behavior_packs").mkdir(exist_ok=True)
    
    # Create a dummy world for realism, matching the properties file
    world_db_dir = target / "worlds" / "Bedrock level" / "db"
    world_db_dir.mkdir(parents=True, exist_ok=True)

