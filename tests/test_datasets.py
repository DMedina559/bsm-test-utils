import os
import shutil
import zipfile
from pathlib import Path

import pytest

from bsm_test_utils.datasets import (
    SYNTHETIC_DB_NOTICE,
    DatasetSpec,
    assert_trees_equal,
    compare_trees,
    create_server_dataset,
    measure_backup_restore,
    mutate_server_dataset,
)


def test_dataset_reproducibility_and_content_profiles(tmp_path):
    spec = DatasetSpec(
        file_count=25,
        total_bytes=64 * 1024,
        profile="mixed",
        seed=12345,
        empty_dir_count=2,
        unicode_names=True,
    )
    res1 = create_server_dataset(tmp_path / "ds1", spec=spec)
    res2 = create_server_dataset(tmp_path / "ds2", spec=spec)

    assert res1.file_count == 25
    assert res1.total_bytes == 64 * 1024
    assert res1.inventory is not None
    assert res2.inventory is not None

    comp = compare_trees(res1.inventory, res2.inventory, check_hashes=True)
    assert comp.ok, comp.summary()

    # Verify synthetic notice is present in world db files
    world_files = [
        p
        for p in (tmp_path / "ds1" / "worlds").rglob("*")
        if p.is_file() and p.stat().st_size >= len(SYNTHETIC_DB_NOTICE)
    ]
    assert world_files
    assert world_files[0].read_bytes().startswith(SYNTHETIC_DB_NOTICE.encode("utf-8"))


def test_dataset_limits_and_presets(tmp_path):
    with pytest.raises(ValueError, match="exceeds max_files_limit"):
        create_server_dataset(
            tmp_path / "too_many",
            spec=DatasetSpec(file_count=100, max_files_limit=10),
        )

    with pytest.raises(ValueError, match="exceeds max_bytes_limit"):
        create_server_dataset(
            tmp_path / "too_big",
            spec=DatasetSpec(total_bytes=2048, max_bytes_limit=1024),
        )

    preset_res = create_server_dataset(
        tmp_path / "preset_small",
        spec=DatasetSpec(preset="many-small-files", file_count=40, total_bytes=16384),
    )
    assert preset_res.file_count == 40
    assert preset_res.total_bytes == 16384


def test_tree_comparison_and_mutation(tmp_path):
    spec = DatasetSpec(file_count=15, total_bytes=32 * 1024, seed=77)
    base_dir = tmp_path / "base"
    clone_dir = tmp_path / "clone"

    create_server_dataset(base_dir, spec=spec)
    shutil.copytree(base_dir, clone_dir)

    assert_trees_equal(base_dir, clone_dir)

    mut = mutate_server_dataset(
        clone_dir, add_count=2, modify_count=2, delete_count=1, seed=99
    )
    assert len(mut.added) == 2
    assert len(mut.modified) == 2
    assert len(mut.deleted) == 1

    diff = compare_trees(base_dir, clone_dir)
    assert not diff.ok
    assert diff.missing == mut.deleted
    assert diff.extra == mut.added
    assert sorted(diff.changed.keys()) == mut.modified

    with pytest.raises(AssertionError, match="Directory restore verification failed"):
        assert_trees_equal(base_dir, clone_dir)


def test_measure_backup_restore_correctness(tmp_path):
    src_dir = tmp_path / "src"
    backups_dir = tmp_path / "backups"
    restores_dir = tmp_path / "restores"
    backups_dir.mkdir()
    restores_dir.mkdir()

    create_server_dataset(
        src_dir,
        spec=DatasetSpec(file_count=20, total_bytes=48 * 1024, seed=101),
    )

    def _backup_cb(source: Path, idx: int) -> Path:
        archive = Path(backups_dir / f"backup_{idx}.zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source):
                rel_root = Path(root).relative_to(source).as_posix()
                if not dirs and not files and rel_root != ".":
                    zf.writestr(rel_root + "/", "")
                for f in files:
                    fp = Path(root) / f
                    zf.write(fp, arcname=fp.relative_to(source).as_posix())
        return archive

    def _restore_cb(idx: int) -> Path:
        archive = Path(backups_dir / f"backup_{idx}.zip")
        dest = Path(restores_dir / f"restore_{idx}")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
        return dest

    summary = measure_backup_restore(
        src_dir,
        backup_fn=_backup_cb,
        restore_fn=_restore_cb,
        runs=2,
        warmup_runs=1,
        verify_restore=True,
        dataset_details={"preset": "unit-test"},
    )

    assert len(summary.runs) == 2
    assert summary.warmup_runs == 1
    assert summary.source_files == 20
    assert summary.source_bytes == 48 * 1024
    assert summary.archive_bytes is not None and summary.archive_bytes > 0
    assert summary.compression_ratio is not None and summary.compression_ratio < 1.0
    assert all(r.verified is True for r in summary.runs)


@pytest.mark.benchmark
def test_large_dataset_benchmark_opt_in(tmp_path, request):
    if not (
        request.config.getoption("--run-benchmarks")
        or os.environ.get("BSM_RUN_BENCHMARKS") == "1"
    ):
        pytest.skip("Large benchmark test is opt-in (use --run-benchmarks).")

    src_dir = tmp_path / "large_src"
    create_server_dataset(
        src_dir,
        spec=DatasetSpec(
            file_count=2_000,
            total_bytes=16 * 1024 * 1024,
            profile="mixed",
            seed=42,
        ),
    )
    assert (src_dir / "worlds").is_dir()
