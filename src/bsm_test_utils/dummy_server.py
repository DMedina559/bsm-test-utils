import os
import platform
import shutil
import zipfile
from pathlib import Path
from typing import List, Union


def create_server_zip(
    target_dir: Union[str, Path],
    version: str = "1.20.0.01",
    is_preview: bool = False,
    is_windows: bool = None,
    filename: str = None
) -> Path:
    """
    Creates a mock bedrock server zip release.
    Packages the Go dummy server binary along with default server properties 
    and configuration files into a zip archive matching the standard release format.
    
    :param target_dir: Where to generate the zip file.
    :param version: The version string to embed in the filename.
    :param is_preview: Whether this is a preview release.
    :param is_windows: Whether to package the Windows binary (default: auto-detect based on host OS).
    :return: Path to the generated zip file.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    
    if is_windows is None:
        is_windows = platform.system() == "Windows"
    
    if filename:
        zip_name = filename
    else:
        os_name = "win" if is_windows else "linux"
        preview_tag = "-preview" if is_preview else ""
        zip_name = f"bedrock-server-{version}{preview_tag}-{os_name}.zip"
    zip_path = target / zip_name
    
    binary_name = "bedrock_server.exe" if is_windows else "bedrock_server"
    
    # Locate data files and built binary
    package_dir = Path(__file__).parent.parent / "bsm_test_utils"
    data_dir = package_dir / "data"
    src_go_binary = Path(__file__).parent.parent.parent / "src_go" / "dummy_server"
    
    if not src_go_binary.exists():
        # Fallback to the one packaged in data if src_go is not available
        src_go_binary = data_dir / binary_name
        
    if not src_go_binary.exists():
        raise FileNotFoundError(
            f"Could not find dummy server binary. Please ensure it is built."
        )
        
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add the binary
        zf.write(src_go_binary, arcname=binary_name)
        
        # Add configs
        configs = ["server.properties", "allowlist.json", "permissions.json"]
        for config in configs:
            config_path = data_dir / config
            if config_path.exists():
                zf.write(config_path, arcname=config)
                
        # Add some empty directories standard in the zip
        zf.writestr("behavior_packs/", "")
        zf.writestr("resource_packs/", "")
        zf.writestr("premium_cache/", "")
        
    return zip_path
