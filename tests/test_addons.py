import json
import zipfile

import pytest

import bsm_test_utils
from bsm_test_utils.addons import (
    PackFaults,
    PackSpec,
    build_pack,
    create_behavior_pack,
    create_checksum_mismatch_archive,
    create_corrupt_archive,
    create_duplicate_entry_archive,
    create_mcaddon,
    create_mcworld,
    create_resource_pack,
    create_script_pack,
    create_traversal_archive,
    write_mcpack,
    write_pack_directory,
)


def test_package_root_exports():
    assert hasattr(bsm_test_utils, "create_mcaddon")
    assert hasattr(bsm_test_utils, "create_mcworld")
    assert hasattr(bsm_test_utils, "create_script_pack")
    assert hasattr(bsm_test_utils, "PackSpec")
    assert hasattr(bsm_test_utils, "DatasetSpec")
    assert hasattr(bsm_test_utils, "create_server_dataset")


def test_create_behavior_pack_dir(tmp_path):
    pack_dir = create_behavior_pack(tmp_path, name="Test BP")
    assert pack_dir is not None and pack_dir.is_dir()
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "scripts" / "main.js").exists()

    with open(pack_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["header"]["name"] == "Test BP"
    assert manifest["modules"][0]["type"] == "data"
    assert "uuid" in manifest["header"]


def test_create_resource_pack_zip(tmp_path):
    pack_zip = create_resource_pack(tmp_path, name="Test RP", as_zip=True)
    assert pack_zip is not None and pack_zip.is_file()
    assert pack_zip.suffix == ".mcpack"

    with zipfile.ZipFile(pack_zip, "r") as zf:
        assert "manifest.json" in zf.namelist()
        assert "textures/item_texture.json" in zf.namelist()

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["header"]["name"] == "Test RP"
        assert manifest["modules"][0]["type"] == "resources"


def test_create_invalid_pack(tmp_path):
    pack_dir = create_behavior_pack(tmp_path, name="Invalid Pack", valid=False)
    assert pack_dir is not None
    with open(pack_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert "uuid" not in manifest.get("header", {})


def test_create_script_pack(tmp_path):
    pack_dir = create_script_pack(
        tmp_path,
        name="Test Script",
        script_entry="scripts/custom.js",
        script_content="console.log('custom');",
    )
    assert pack_dir is not None and pack_dir.is_dir()
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "scripts" / "custom.js").read_text(encoding="utf-8") == (
        "console.log('custom');"
    )


def test_create_mcaddon_and_input_immutability(tmp_path):
    packs = [
        {"name": "My Addon BP", "pack_type": "data"},
        {"name": "My Addon RP", "pack_type": "resources"},
    ]
    original_copy = [dict(p) for p in packs]

    addon1 = create_mcaddon(tmp_path / "one", name="My Addon", packs=packs)
    # Input dictionaries must not be mutated (no 'out_zip' or 'as_zip' injected)
    assert packs == original_copy

    # Reusing the exact same packs list in create_mcaddon and create_mcworld must succeed
    addon2 = create_mcaddon(tmp_path / "two", name="My Addon", packs=packs)
    world1 = create_mcworld(tmp_path / "three", name="My World", packs=packs)

    assert addon1.exists()
    assert addon2.exists()
    assert world1.exists()

    with zipfile.ZipFile(addon1, "r") as zf:
        namelist = zf.namelist()
        assert "my_addon_bp_data.mcpack" in namelist
        assert "my_addon_rp_resources.mcpack" in namelist


def test_create_mcworld_binary_and_text_level_dat(tmp_path):
    binary_payload = b"\x08\x00\x00\x00\x10\x00\x00\x00NBT_BINARY_LEVEL_DAT"
    world_path = create_mcworld(
        tmp_path,
        name="Binary World",
        level_dat_content=binary_payload,
        packs=[{"name": "embedded_bp", "pack_type": "data"}],
    )
    assert world_path.exists()
    assert world_path.suffix == ".mcworld"

    with zipfile.ZipFile(world_path, "r") as zf:
        namelist = zf.namelist()
        assert "level.dat" in namelist
        assert zf.read("level.dat") == binary_payload
        assert "behavior_packs/embedded_bp_data/manifest.json" in namelist


def test_path_escape_rejection(tmp_path):
    for unsafe_name in ["../escaped", "..\\escaped", "sub/nested", "/abs/path"]:
        with pytest.raises(ValueError, match="Unsafe|Absolute|Invalid"):
            create_behavior_pack(tmp_path, name=unsafe_name)
        with pytest.raises(ValueError, match="Unsafe|Absolute|Invalid"):
            create_mcaddon(tmp_path, name=unsafe_name)
        with pytest.raises(ValueError, match="Unsafe|Absolute|Invalid"):
            create_mcworld(tmp_path, name=unsafe_name)


def test_duplicate_pack_names_rejected(tmp_path):
    packs = [
        PackSpec(name="Same Name", pack_type="data"),
        PackSpec(name="same_name", pack_type="data"),
    ]
    with pytest.raises(ValueError, match="Duplicate normalized pack name"):
        create_mcaddon(tmp_path, name="DupBundle", packs=packs)


def test_build_pack_reuse_and_specific_faults(tmp_path):
    spec = PackSpec(
        name="Reusable Pack",
        pack_type="data",
        version=(2, 1, 0),
        min_engine_version=(1, 20, 0),
        header_uuid="11111111-2222-3333-4444-555555555555",
        module_uuid="66666666-7777-8888-9999-000000000000",
        dependencies=[
            {"uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "version": [1, 0, 0]}
        ],
    )
    built = build_pack(spec)

    dir_out = write_pack_directory(tmp_path / "dir", built)
    zip_out = write_mcpack(tmp_path / "zip", built)

    assert (dir_out / "manifest.json").read_bytes() == built.manifest_bytes
    with zipfile.ZipFile(zip_out, "r") as zf:
        assert zf.read("manifest.json") == built.manifest_bytes

    # Specific faults: unsupported format version & invalid version
    fault_spec = PackSpec(
        name="Faulty Pack",
        faults=PackFaults(unsupported_format_version=99, invalid_version=True),
    )
    fault_built = build_pack(fault_spec)
    assert fault_built.manifest_data is not None
    assert fault_built.manifest_data["format_version"] == 99
    assert fault_built.manifest_data["header"]["version"] == "not-a-version-array"


def test_archive_failure_fixtures(tmp_path):
    corrupt_not_zip = create_corrupt_archive(
        tmp_path, filename="bad1.mcpack", mode="not_a_zip"
    )
    assert not zipfile.is_zipfile(corrupt_not_zip)

    corrupt_trunc = create_corrupt_archive(
        tmp_path, filename="bad2.mcpack", mode="truncated_zip"
    )
    with pytest.raises(zipfile.BadZipFile):
        with zipfile.ZipFile(corrupt_trunc, "r") as zf:
            zf.namelist()

    trav = create_traversal_archive(
        tmp_path, filename="trav.zip", traversal_entry="../outside.txt"
    )
    with zipfile.ZipFile(trav, "r") as zf:
        assert "../outside.txt" in zf.namelist()

    dup = create_duplicate_entry_archive(tmp_path, filename="dup.mcpack")
    with zipfile.ZipFile(dup, "r") as zf:
        assert zf.namelist().count("manifest.json") == 2

    crc_bad = create_checksum_mismatch_archive(tmp_path, filename="crc.zip")
    with zipfile.ZipFile(crc_bad, "r") as zf:
        assert zf.testzip() == "data.txt"
        with pytest.raises(zipfile.BadZipFile):
            zf.read("data.txt")
