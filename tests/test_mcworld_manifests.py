import json
import zipfile

from bsm_test_utils.addons import create_mcworld


def test_mcworld_pack_manifests(tmp_path):
    """
    Tests that create_mcworld correctly generates world_behavior_packs.json
    and world_resource_packs.json based on embedded packs.
    """
    packs = [
        {"name": "My BP", "pack_type": "data", "version": [1, 2, 3]},
        {"name": "My RP", "pack_type": "resources", "version": [2, 0, 0]},
    ]
    world_zip = create_mcworld(tmp_path, name="ManifestWorld", packs=packs)

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(world_zip, "r") as zf:
        zf.extractall(extract_dir)

    world_dir = extract_dir

    bp_manifest_path = world_dir / "world_behavior_packs.json"
    rp_manifest_path = world_dir / "world_resource_packs.json"

    assert bp_manifest_path.exists()
    assert rp_manifest_path.exists()

    with open(bp_manifest_path) as f:
        bp_manifest = json.load(f)
    with open(rp_manifest_path) as f:
        rp_manifest = json.load(f)

    assert len(bp_manifest) == 1
    assert "pack_id" in bp_manifest[0]
    assert bp_manifest[0]["version"] == [1, 2, 3]

    assert len(rp_manifest) == 1
    assert "pack_id" in rp_manifest[0]
    assert rp_manifest[0]["version"] == [2, 0, 0]
