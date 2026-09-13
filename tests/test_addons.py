import json
import zipfile

from bsm_test_utils.addons import (
    create_behavior_pack,
    create_mcaddon,
    create_mcworld,
    create_resource_pack,
    create_script_pack,
)


def test_create_behavior_pack_dir(tmp_path):
    pack_dir = create_behavior_pack(tmp_path, name="Test BP")
    assert pack_dir.is_dir()
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "scripts" / "main.js").exists()

    with open(pack_dir / "manifest.json") as f:
        manifest = json.load(f)
    assert manifest["header"]["name"] == "Test BP"
    assert manifest["modules"][0]["type"] == "data"
    assert "uuid" in manifest["header"]


def test_create_resource_pack_zip(tmp_path):
    pack_zip = create_resource_pack(tmp_path, name="Test RP", as_zip=True)
    assert pack_zip.is_file()
    assert pack_zip.suffix == ".mcpack"

    with zipfile.ZipFile(pack_zip, "r") as zf:
        assert "manifest.json" in zf.namelist()
        assert "textures/item_texture.json" in zf.namelist()

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["header"]["name"] == "Test RP"
        assert manifest["modules"][0]["type"] == "resources"


def test_create_invalid_pack(tmp_path):
    pack_dir = create_behavior_pack(tmp_path, name="Invalid Pack", valid=False)
    with open(pack_dir / "manifest.json") as f:
        manifest = json.load(f)
    assert "uuid" not in manifest.get("header", {})


def test_create_script_pack(tmp_path):
    pack_dir = create_script_pack(tmp_path, name="Test Script")
    assert pack_dir.is_dir()
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "scripts" / "main.js").exists()


def test_create_mcaddon(tmp_path):
    addon_path = create_mcaddon(tmp_path, name="My Addon")
    assert addon_path.exists()
    assert addon_path.suffix == ".mcaddon"

    with zipfile.ZipFile(addon_path, "r") as zf:
        namelist = zf.namelist()
        assert "my_addon_bp_data.mcpack" in namelist
        assert "my_addon_rp_resources.mcpack" in namelist


def test_create_mcworld(tmp_path):
    world_path = create_mcworld(
        tmp_path, name="My World", packs=[{"name": "embedded_bp", "pack_type": "data"}]
    )
    assert world_path.exists()
    assert world_path.suffix == ".mcworld"

    with zipfile.ZipFile(world_path, "r") as zf:
        namelist = zf.namelist()
        assert "level.dat" in namelist
        assert "behavior_packs/embedded_bp_data/manifest.json" in namelist
