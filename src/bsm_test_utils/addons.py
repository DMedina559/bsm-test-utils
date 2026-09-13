import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Union


def _generate_manifest(
    name: str,
    description: str,
    uuid1: str,
    uuid2: str,
    version: List[int],
    pack_type: str,
) -> dict:
    return {
        "format_version": 2,
        "header": {
            "name": name,
            "description": description,
            "uuid": uuid1,
            "version": version,
            "min_engine_version": [1, 16, 0],
        },
        "modules": [{"type": pack_type, "uuid": uuid2, "version": version}],
    }


def create_addon(
    target_dir: Optional[Union[str, Path]] = None,
    name: str = "Test Addon",
    pack_type: str = "data",
    valid: bool = True,
    version: Optional[List[int]] = None,
    as_zip: bool = False,
    invalid_json: bool = False,
    out_zip: Optional[zipfile.ZipFile] = None,
) -> Optional[Path]:
    """
    Dynamically generates a Bedrock addon (behavior pack, resource pack, or script pack).

    :param target_dir: Where to generate the addon.
    :param name: Name of the addon.
    :param pack_type: "data" for behavior pack, "resources" for resource pack, "script" for script pack.
    :param valid: If False, generates an invalid manifest (e.g. missing uuid).
    :param version: Version list like [1, 0, 0].
    :param as_zip: If True, creates a .zip file (or .mcpack). If False, creates a directory.
    :param invalid_json: If True, generates a manifest with broken JSON syntax.
    :return: Path to the generated addon (directory or zip).
    """
    if target_dir is not None:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
    else:
        target = None

    version = version or [1, 0, 0]
    uuid1 = str(uuid.uuid4()) if valid else "invalid-uuid"
    uuid2 = str(uuid.uuid4()) if valid else "invalid-uuid"

    manifest = _generate_manifest(
        name, f"Dummy {pack_type} pack", uuid1, uuid2, version, pack_type
    )

    if not valid:
        # Mess up the manifest to make it invalid
        if "header" in manifest:
            del manifest["header"]["uuid"]

    addon_name = f"{name.replace(' ', '_').lower()}_{pack_type}"

    manifest_str = json.dumps(manifest, indent=2)
    if invalid_json:
        manifest_str = manifest_str[
            :-5
        ]  # Strip off the closing braces to break the JSON syntax

    if as_zip:
        if out_zip is not None:
            # Create in-memory zip
            import io

            mem_zip_buffer = io.BytesIO()
            with zipfile.ZipFile(mem_zip_buffer, "w") as zf:
                zf.writestr("manifest.json", manifest_str)
                if pack_type == "data" or pack_type == "script":
                    zf.writestr("scripts/main.js", "console.log('dummy script');")
                else:
                    zf.writestr("textures/item_texture.json", "{}")
            # Write out to parent zip
            out_zip.writestr(f"{addon_name}.mcpack", mem_zip_buffer.getvalue())
            return None
        else:
            if target is None:
                raise ValueError("target_dir is required if out_zip is None")
            zip_path = target / f"{addon_name}.mcpack"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("manifest.json", manifest_str)
                if pack_type == "data" or pack_type == "script":
                    zf.writestr("scripts/main.js", "console.log('dummy script');")
                else:
                    zf.writestr("textures/item_texture.json", "{}")
            return zip_path
    else:
        if out_zip is not None:
            out_zip.writestr(f"{addon_name}/manifest.json", manifest_str)
            if pack_type == "data" or pack_type == "script":
                out_zip.writestr(
                    f"{addon_name}/scripts/main.js", "console.log('dummy script');"
                )
            else:
                out_zip.writestr(f"{addon_name}/textures/item_texture.json", "{}")
            return None
        else:
            if target is None:
                raise ValueError("target_dir is required if out_zip is None")
            pack_dir = target / addon_name
            pack_dir.mkdir(parents=True, exist_ok=True)
            with open(pack_dir / "manifest.json", "w") as f:
                f.write(manifest_str)

            if pack_type == "data" or pack_type == "script":
                (pack_dir / "scripts").mkdir(exist_ok=True)
                with open(pack_dir / "scripts" / "main.js", "w") as f:
                    f.write("console.log('dummy script');")
            else:
                (pack_dir / "textures").mkdir(exist_ok=True)
                with open(pack_dir / "textures" / "item_texture.json", "w") as f:
                    f.write("{}")
            return pack_dir


def create_behavior_pack(
    target_dir: Optional[Union[str, Path]] = None, **kwargs
) -> Optional[Path]:
    """Helper to create a behavior pack."""
    kwargs["pack_type"] = "data"
    return create_addon(target_dir, **kwargs)


def create_resource_pack(
    target_dir: Optional[Union[str, Path]] = None, **kwargs
) -> Optional[Path]:
    """Helper to create a resource pack."""
    kwargs["pack_type"] = "resources"
    return create_addon(target_dir, **kwargs)


def create_script_pack(
    target_dir: Optional[Union[str, Path]] = None, **kwargs
) -> Optional[Path]:
    """Helper to create a script pack."""
    kwargs["pack_type"] = "script"
    return create_addon(target_dir, **kwargs)


def create_mcaddon(
    target_dir: Union[str, Path],
    name: str = "Test McAddon",
    packs: Optional[List[dict]] = None,
) -> Path:
    """
    Creates an .mcaddon file containing multiple packs (.mcpack files).

    :param target_dir: Where to generate the .mcaddon file.
    :param name: Base name of the file (e.g. 'Test McAddon' becomes 'test_mcaddon.mcaddon').
    :param packs: A list of dicts with kwargs for `create_addon`. If None, generates one BP and one RP.
    :return: Path to the generated .mcaddon file.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    addon_name = f"{name.replace(' ', '_').lower()}.mcaddon"
    mcaddon_path = target / addon_name

    if packs is None:
        packs = [
            {"name": f"{name} BP", "pack_type": "data"},
            {"name": f"{name} RP", "pack_type": "resources"},
        ]

    # Bundle them into the .mcaddon
    with zipfile.ZipFile(mcaddon_path, "w") as mcaddon_zf:
        for pack_kwargs in packs:
            pack_kwargs["as_zip"] = True
            pack_kwargs["out_zip"] = mcaddon_zf
            create_addon(**pack_kwargs)

    return mcaddon_path


def create_mcworld(
    target_dir: Union[str, Path],
    name: str = "Test World",
    level_dat_content: str = "dummy level data",
    packs: Optional[List[dict]] = None,
) -> Path:
    """
    Creates an .mcworld file (a zip containing a world, optionally with embedded packs).

    :param target_dir: Where to generate the .mcworld file.
    :param name: Base name of the file (e.g. 'Test World' becomes 'test_world.mcworld').
    :param level_dat_content: String to put in level.dat.
    :param packs: Optional list of dicts with kwargs for `create_addon`.
    :return: Path to the generated .mcworld file.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    world_name = f"{name.replace(' ', '_').lower()}.mcworld"
    mcworld_path = target / world_name

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create world structure
        world_dir = Path(tmpdir) / name
        world_dir.mkdir()

        # level.dat
        with open(world_dir / "level.dat", "w") as f:
            f.write(level_dat_content)

        # Addons in behavior_packs / resource_packs if specified
        if packs:
            bp_dir = world_dir / "behavior_packs"
            rp_dir = world_dir / "resource_packs"

            world_behavior_packs = []
            world_resource_packs = []

            for pack_kwargs in packs:
                pack_kwargs["as_zip"] = (
                    False  # worlds usually contain extracted folders
                )
                pack_type = pack_kwargs.get("pack_type", "data")

                if pack_type == "data" or pack_type == "script":
                    pack_path = create_addon(bp_dir, **pack_kwargs)
                    if pack_path is not None:
                        manifest_path = pack_path / "manifest.json"
                        if manifest_path.exists():
                            with open(manifest_path, "r") as f:
                                try:
                                    manifest_data = json.load(f)
                                    if (
                                        "header" in manifest_data
                                        and "uuid" in manifest_data["header"]
                                        and "version" in manifest_data["header"]
                                    ):
                                        world_behavior_packs.append(
                                            {
                                                "pack_id": manifest_data["header"][
                                                    "uuid"
                                                ],
                                                "version": manifest_data["header"][
                                                    "version"
                                                ],
                                            }
                                        )
                                except json.JSONDecodeError:
                                    pass
                else:
                    pack_path = create_addon(rp_dir, **pack_kwargs)
                    if pack_path is not None:
                        manifest_path = pack_path / "manifest.json"
                        if manifest_path.exists():
                            with open(manifest_path, "r") as f:
                                try:
                                    manifest_data = json.load(f)
                                    if (
                                        "header" in manifest_data
                                        and "uuid" in manifest_data["header"]
                                        and "version" in manifest_data["header"]
                                    ):
                                        world_resource_packs.append(
                                            {
                                                "pack_id": manifest_data["header"][
                                                    "uuid"
                                                ],
                                                "version": manifest_data["header"][
                                                    "version"
                                                ],
                                            }
                                        )
                                except json.JSONDecodeError:
                                    pass

            # Write world pack manifests
            if world_behavior_packs:
                with open(world_dir / "world_behavior_packs.json", "w") as f:
                    json.dump(world_behavior_packs, f, indent=4)
            if world_resource_packs:
                with open(world_dir / "world_resource_packs.json", "w") as f:
                    json.dump(world_resource_packs, f, indent=4)

        # Zip it up as .mcworld
        with zipfile.ZipFile(mcworld_path, "w") as mcworld_zf:
            for root, dirs, files in os.walk(world_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, world_dir)
                    mcworld_zf.write(file_path, arcname=arcname)

    return mcworld_path
