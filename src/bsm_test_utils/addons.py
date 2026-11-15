import hashlib
import io
import json
import os
import re
import tempfile
import uuid
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

PackType = Literal["data", "resources", "script"]


@dataclass
class PackFaults:
    """Deliberate manifest or archive defects for negative testing."""

    missing_header: bool = False
    missing_uuid: bool = False
    invalid_uuid: bool = False
    missing_module_uuid: bool = False
    invalid_version: bool = False
    unsupported_format_version: Optional[int] = None
    malformed_json: bool = False
    missing_manifest: bool = False
    corrupt_zip: bool = False
    duplicate_entries: bool = False
    traversal_entry: Optional[str] = None
    extra_entries: Dict[str, Union[str, bytes]] = field(default_factory=dict)


@dataclass
class PackSpec:
    """Specification for building a Bedrock add-on pack."""

    name: str = "Test Addon"
    pack_type: str = "data"
    description: Optional[str] = None
    version: Tuple[int, int, int] = (1, 0, 0)
    min_engine_version: Tuple[int, int, int] = (1, 16, 0)
    header_uuid: Optional[str] = None
    module_uuid: Optional[str] = None
    dependencies: List[Dict[str, Any]] = field(default_factory=list)
    script_entry: str = "scripts/main.js"
    script_content: str = "console.log('dummy script');"
    extra_files: Dict[str, Union[str, bytes]] = field(default_factory=dict)
    directory_name: Optional[str] = None
    faults: PackFaults = field(default_factory=PackFaults)


@dataclass
class BuiltPack:
    """In-memory representation of a constructed pack."""

    spec: PackSpec
    slug: str
    manifest_data: Optional[Dict[str, Any]]
    manifest_bytes: Optional[bytes]
    files: Dict[str, bytes]
    sha256: str


def sanitize_filename(name: str, allow_empty: bool = False) -> str:
    """
    Sanitizes a display name into a safe single-segment filename/slug.
    Raises ValueError if the name attempts path traversal or resolves to an unsafe target.
    """
    if not isinstance(name, str):
        raise TypeError("Name must be a string")

    raw = name.strip()
    if not raw:
        if allow_empty:
            return ""
        raise ValueError("Name cannot be empty")

    # Reject explicit path separators or traversal components
    if "/" in raw or "\\" in raw or raw in {".", ".."} or ".." in Path(raw).parts:
        raise ValueError(f"Unsafe path characters or traversal in name: {name!r}")

    if os.path.isabs(raw) or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError(f"Absolute or drive-qualified name is not allowed: {name!r}")

    slug = re.sub(r"\s+", "_", raw.lower())
    slug = re.sub(r"[^a-z0-9_.-]", "_", slug)
    slug = slug.strip("._")
    if not slug or slug in {".", ".."}:
        raise ValueError(f"Name {name!r} does not produce a valid filename")
    return slug


def validate_child_path(base_dir: Path, child_name: str) -> Path:
    """Ensures child_name resolves strictly inside base_dir."""
    base_resolved = base_dir.resolve()
    if "/" in child_name or "\\" in child_name or child_name in {".", ".."}:
        raise ValueError(
            f"Invalid filename {child_name!r}: must be a single path segment"
        )
    candidate = (base_resolved / child_name).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Path {child_name!r} escapes target directory {base_dir}"
        ) from exc
    if candidate == base_resolved:
        raise ValueError(f"Path {child_name!r} resolves to target directory itself")
    return candidate


def _generate_manifest(
    name: str,
    description: str,
    uuid1: str,
    uuid2: str,
    version: List[int],
    pack_type: str,
    min_engine_version: Optional[List[int]] = None,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    format_version: int = 2,
    script_entry: Optional[str] = None,
) -> Dict[str, Any]:
    module: Dict[str, Any] = {
        "type": pack_type,
        "uuid": uuid2,
        "version": list(version),
    }
    if pack_type == "script" and script_entry:
        module["entry"] = script_entry
        module["language"] = "javascript"

    manifest: Dict[str, Any] = {
        "format_version": format_version,
        "header": {
            "name": name,
            "description": description,
            "uuid": uuid1,
            "version": list(version),
            "min_engine_version": list(min_engine_version or [1, 16, 0]),
        },
        "modules": [module],
    }
    if dependencies:
        manifest["dependencies"] = [dict(dep) for dep in dependencies]
    return manifest


def _coerce_pack_spec(
    spec_or_dict: Union[PackSpec, Dict[str, Any]],
) -> PackSpec:
    if isinstance(spec_or_dict, PackSpec):
        return spec_or_dict
    if not isinstance(spec_or_dict, dict):
        raise TypeError(f"Expected PackSpec or dict, got {type(spec_or_dict)!r}")

    data = dict(spec_or_dict)
    # Strip legacy internal keys if caller passed a mutated dict
    data.pop("as_zip", None)
    data.pop("out_zip", None)
    data.pop("target_dir", None)

    valid = data.pop("valid", True)
    invalid_json = data.pop("invalid_json", False)
    faults = data.pop("faults", None)
    if faults is None:
        faults = PackFaults(
            missing_uuid=not valid,
            invalid_uuid=not valid,
            malformed_json=bool(invalid_json),
        )
    elif isinstance(faults, dict):
        faults = PackFaults(**faults)

    version_raw = data.pop("version", None)
    version: Tuple[int, int, int] = (
        (int(version_raw[0]), int(version_raw[1]), int(version_raw[2]))
        if version_raw is not None and len(version_raw) == 3
        else (1, 0, 0)
    )
    min_engine_raw = data.pop("min_engine_version", None)
    min_engine: Tuple[int, int, int] = (
        (int(min_engine_raw[0]), int(min_engine_raw[1]), int(min_engine_raw[2]))
        if min_engine_raw is not None and len(min_engine_raw) == 3
        else (1, 16, 0)
    )

    return PackSpec(
        name=data.pop("name", "Test Addon"),
        pack_type=data.pop("pack_type", "data"),
        description=data.pop("description", None),
        version=version,
        min_engine_version=min_engine,
        header_uuid=data.pop("header_uuid", None),
        module_uuid=data.pop("module_uuid", None),
        dependencies=list(data.pop("dependencies", [])),
        script_entry=data.pop("script_entry", "scripts/main.js"),
        script_content=data.pop("script_content", "console.log('dummy script');"),
        extra_files=dict(data.pop("extra_files", {})),
        directory_name=data.pop("directory_name", None),
        faults=faults,
    )


def build_pack(spec: Union[PackSpec, Dict[str, Any]]) -> BuiltPack:
    """
    Constructs a pack's manifest and payload files in memory from a PackSpec.
    Can be reused across directory and archive writers.
    """
    pack_spec = _coerce_pack_spec(spec)
    faults = pack_spec.faults

    if pack_spec.directory_name is not None:
        slug = sanitize_filename(pack_spec.directory_name)
    else:
        base_slug = sanitize_filename(pack_spec.name)
        type_slug = sanitize_filename(pack_spec.pack_type)
        slug = f"{base_slug}_{type_slug}"

    uuid1 = pack_spec.header_uuid or (
        "invalid-uuid" if faults.invalid_uuid else str(uuid.uuid4())
    )
    uuid2 = pack_spec.module_uuid or (
        "invalid-uuid" if faults.invalid_uuid else str(uuid.uuid4())
    )
    description = (
        pack_spec.description
        if pack_spec.description is not None
        else f"Dummy {pack_spec.pack_type} pack"
    )
    format_version = (
        faults.unsupported_format_version
        if faults.unsupported_format_version is not None
        else 2
    )

    manifest: Dict[str, Any] = _generate_manifest(
        name=pack_spec.name,
        description=description,
        uuid1=uuid1,
        uuid2=uuid2,
        version=list(pack_spec.version),
        pack_type=pack_spec.pack_type,
        min_engine_version=list(pack_spec.min_engine_version),
        dependencies=pack_spec.dependencies,
        format_version=format_version,
        script_entry=(
            pack_spec.script_entry if pack_spec.pack_type == "script" else None
        ),
    )

    if faults.invalid_version:
        manifest["header"]["version"] = "not-a-version-array"
        if manifest.get("modules"):
            manifest["modules"][0]["version"] = "not-a-version-array"

    if faults.missing_uuid and "header" in manifest:
        manifest["header"].pop("uuid", None)

    if faults.missing_module_uuid and manifest.get("modules"):
        manifest["modules"][0].pop("uuid", None)

    if faults.missing_header:
        manifest.pop("header", None)

    files: Dict[str, bytes] = {}
    manifest_bytes: Optional[bytes] = None
    manifest_data: Optional[Dict[str, Any]] = None

    if not faults.missing_manifest:
        manifest_str = json.dumps(manifest, indent=2)
        if faults.malformed_json:
            manifest_str = manifest_str[:-5]
        else:
            manifest_data = manifest
        manifest_bytes = manifest_str.encode("utf-8")
        files["manifest.json"] = manifest_bytes

    if pack_spec.pack_type in ("data", "script"):
        entry_path = pack_spec.script_entry.lstrip("/")
        files[entry_path] = pack_spec.script_content.encode("utf-8")
    else:
        files["textures/item_texture.json"] = b"{}"

    for rel_path, content in pack_spec.extra_files.items():
        norm_rel = rel_path.replace("\\", "/").lstrip("/")
        if ".." in Path(norm_rel).parts:
            raise ValueError(f"Unsafe extra_files path: {rel_path!r}")
        files[norm_rel] = (
            content.encode("utf-8") if isinstance(content, str) else bytes(content)
        )

    for rel_path, content in faults.extra_entries.items():
        files[rel_path] = (
            content.encode("utf-8") if isinstance(content, str) else bytes(content)
        )

    hasher = hashlib.sha256()
    for rel_path in sorted(files):
        hasher.update(rel_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(files[rel_path])
        hasher.update(b"\0")

    return BuiltPack(
        spec=pack_spec,
        slug=slug,
        manifest_data=manifest_data,
        manifest_bytes=manifest_bytes,
        files=files,
        sha256=hasher.hexdigest(),
    )


def _pack_to_zip_bytes(built: BuiltPack) -> bytes:
    faults = built.spec.faults
    if faults.corrupt_zip:
        return b"PK\x03\x04corrupt-zip-payload-not-a-valid-archive"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, data in built.files.items():
            zf.writestr(rel_path, data)
            if faults.duplicate_entries and rel_path == "manifest.json":
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    zf.writestr(rel_path, data)
        if faults.traversal_entry:
            zf.writestr(faults.traversal_entry, b"traversal-payload")
    return buf.getvalue()


def write_pack_directory(
    target_dir: Union[str, Path],
    pack: Union[PackSpec, BuiltPack, Dict[str, Any]],
    directory_name: Optional[str] = None,
) -> Path:
    """
    Writes a pack as an extracted directory inside target_dir and returns its Path.
    """
    built = pack if isinstance(pack, BuiltPack) else build_pack(pack)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    dir_slug = (
        sanitize_filename(directory_name) if directory_name is not None else built.slug
    )
    pack_dir = validate_child_path(target, dir_slug)
    pack_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, data in built.files.items():
        norm_parts = Path(rel_path).parts
        if ".." in norm_parts or os.path.isabs(rel_path):
            raise ValueError(
                f"Cannot write unsafe path {rel_path!r} when extracting directory"
            )
        dest_file = (pack_dir / rel_path).resolve()
        try:
            dest_file.relative_to(pack_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"File {rel_path!r} escapes pack directory {pack_dir}"
            ) from exc
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(data)

    return pack_dir


def write_mcpack(
    target_dir: Union[str, Path],
    pack: Union[PackSpec, BuiltPack, Dict[str, Any]],
    filename: Optional[str] = None,
) -> Path:
    """
    Writes a pack as a .mcpack archive inside target_dir and returns its Path.
    """
    built = pack if isinstance(pack, BuiltPack) else build_pack(pack)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if filename is not None:
        clean_name = sanitize_filename(
            filename[:-7] if filename.endswith(".mcpack") else filename
        )
        archive_name = (
            filename if filename.endswith(".mcpack") else f"{clean_name}.mcpack"
        )
        validate_child_path(target, archive_name)
    else:
        archive_name = f"{built.slug}.mcpack"

    zip_path = validate_child_path(target, archive_name)
    zip_path.write_bytes(_pack_to_zip_bytes(built))
    return zip_path


def _write_pack_into_zip(
    out_zip: zipfile.ZipFile,
    built: BuiltPack,
    as_zip: bool,
) -> None:
    if as_zip:
        out_zip.writestr(f"{built.slug}.mcpack", _pack_to_zip_bytes(built))
    else:
        for rel_path, data in built.files.items():
            out_zip.writestr(f"{built.slug}/{rel_path}", data)


def create_addon(
    target_dir: Optional[Union[str, Path]] = None,
    name: str = "Test Addon",
    pack_type: str = "data",
    valid: bool = True,
    version: Optional[Sequence[int]] = None,
    as_zip: bool = False,
    invalid_json: bool = False,
    out_zip: Optional[zipfile.ZipFile] = None,
    *,
    description: Optional[str] = None,
    header_uuid: Optional[str] = None,
    module_uuid: Optional[str] = None,
    min_engine_version: Optional[Sequence[int]] = None,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    script_entry: str = "scripts/main.js",
    script_content: str = "console.log('dummy script');",
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
    faults: Optional[PackFaults] = None,
) -> Optional[Path]:
    """
    Dynamically generates a Bedrock addon (behavior pack, resource pack, or script pack).
    Compatibility wrapper around PackSpec, build_pack, write_pack_directory, and write_mcpack.
    """
    ver_tuple: Tuple[int, int, int] = (
        (int(version[0]), int(version[1]), int(version[2]))
        if version is not None and len(version) == 3
        else (1, 0, 0)
    )
    engine_tuple: Tuple[int, int, int] = (
        (
            int(min_engine_version[0]),
            int(min_engine_version[1]),
            int(min_engine_version[2]),
        )
        if min_engine_version is not None and len(min_engine_version) == 3
        else (1, 16, 0)
    )
    effective_faults = faults or PackFaults(
        missing_uuid=not valid,
        invalid_uuid=not valid,
        malformed_json=invalid_json,
    )
    spec = PackSpec(
        name=name,
        pack_type=pack_type,
        description=description,
        version=ver_tuple,
        min_engine_version=engine_tuple,
        header_uuid=header_uuid,
        module_uuid=module_uuid,
        dependencies=list(dependencies or []),
        script_entry=script_entry,
        script_content=script_content,
        extra_files=dict(extra_files or {}),
        faults=effective_faults,
    )
    built = build_pack(spec)

    if out_zip is not None:
        _write_pack_into_zip(out_zip, built, as_zip=as_zip)
        return None

    if target_dir is None:
        raise ValueError("target_dir is required if out_zip is None")

    if as_zip:
        return write_mcpack(target_dir, built)
    return write_pack_directory(target_dir, built)


def create_behavior_pack(
    target_dir: Optional[Union[str, Path]] = None,
    name: str = "Test Addon",
    valid: bool = True,
    version: Optional[Sequence[int]] = None,
    as_zip: bool = False,
    invalid_json: bool = False,
    out_zip: Optional[zipfile.ZipFile] = None,
    *,
    description: Optional[str] = None,
    header_uuid: Optional[str] = None,
    module_uuid: Optional[str] = None,
    min_engine_version: Optional[Sequence[int]] = None,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
    faults: Optional[PackFaults] = None,
) -> Optional[Path]:
    """Helper to create a behavior pack."""
    return create_addon(
        target_dir=target_dir,
        name=name,
        pack_type="data",
        valid=valid,
        version=version,
        as_zip=as_zip,
        invalid_json=invalid_json,
        out_zip=out_zip,
        description=description,
        header_uuid=header_uuid,
        module_uuid=module_uuid,
        min_engine_version=min_engine_version,
        dependencies=dependencies,
        extra_files=extra_files,
        faults=faults,
    )


def create_resource_pack(
    target_dir: Optional[Union[str, Path]] = None,
    name: str = "Test Addon",
    valid: bool = True,
    version: Optional[Sequence[int]] = None,
    as_zip: bool = False,
    invalid_json: bool = False,
    out_zip: Optional[zipfile.ZipFile] = None,
    *,
    description: Optional[str] = None,
    header_uuid: Optional[str] = None,
    module_uuid: Optional[str] = None,
    min_engine_version: Optional[Sequence[int]] = None,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
    faults: Optional[PackFaults] = None,
) -> Optional[Path]:
    """Helper to create a resource pack."""
    return create_addon(
        target_dir=target_dir,
        name=name,
        pack_type="resources",
        valid=valid,
        version=version,
        as_zip=as_zip,
        invalid_json=invalid_json,
        out_zip=out_zip,
        description=description,
        header_uuid=header_uuid,
        module_uuid=module_uuid,
        min_engine_version=min_engine_version,
        dependencies=dependencies,
        extra_files=extra_files,
        faults=faults,
    )


def create_script_pack(
    target_dir: Optional[Union[str, Path]] = None,
    name: str = "Test Addon",
    valid: bool = True,
    version: Optional[Sequence[int]] = None,
    as_zip: bool = False,
    invalid_json: bool = False,
    out_zip: Optional[zipfile.ZipFile] = None,
    *,
    description: Optional[str] = None,
    header_uuid: Optional[str] = None,
    module_uuid: Optional[str] = None,
    min_engine_version: Optional[Sequence[int]] = None,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    script_entry: str = "scripts/main.js",
    script_content: str = "console.log('dummy script');",
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
    faults: Optional[PackFaults] = None,
) -> Optional[Path]:
    """Helper to create a script pack."""
    return create_addon(
        target_dir=target_dir,
        name=name,
        pack_type="script",
        valid=valid,
        version=version,
        as_zip=as_zip,
        invalid_json=invalid_json,
        out_zip=out_zip,
        description=description,
        header_uuid=header_uuid,
        module_uuid=module_uuid,
        min_engine_version=min_engine_version,
        dependencies=dependencies,
        script_entry=script_entry,
        script_content=script_content,
        extra_files=extra_files,
        faults=faults,
    )


def _resolve_built_packs(
    packs: Sequence[Union[PackSpec, BuiltPack, Dict[str, Any]]],
) -> List[BuiltPack]:
    built_packs: List[BuiltPack] = []
    seen_slugs = set()
    for item in packs:
        built = item if isinstance(item, BuiltPack) else build_pack(item)
        if built.slug in seen_slugs:
            raise ValueError(f"Duplicate normalized pack name {built.slug!r} in bundle")
        seen_slugs.add(built.slug)
        built_packs.append(built)
    return built_packs


def create_mcaddon(
    target_dir: Union[str, Path],
    name: str = "Test McAddon",
    packs: Optional[Sequence[Union[PackSpec, BuiltPack, Dict[str, Any]]]] = None,
    *,
    as_mcpacks: bool = True,
) -> Path:
    """
    Creates an .mcaddon file containing multiple packs (.mcpack files or folders).
    Does not mutate caller-supplied pack dictionaries or specifications.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    addon_slug = sanitize_filename(name)
    mcaddon_path = validate_child_path(target, f"{addon_slug}.mcaddon")

    if packs is None:
        raw_packs: Sequence[Union[PackSpec, BuiltPack, Dict[str, Any]]] = [
            PackSpec(name=f"{name} BP", pack_type="data"),
            PackSpec(name=f"{name} RP", pack_type="resources"),
        ]
    else:
        raw_packs = list(packs)

    built_packs = _resolve_built_packs(raw_packs)

    with zipfile.ZipFile(mcaddon_path, "w", zipfile.ZIP_DEFLATED) as mcaddon_zf:
        for built in built_packs:
            _write_pack_into_zip(mcaddon_zf, built, as_zip=as_mcpacks)

    return mcaddon_path


def create_mcworld(
    target_dir: Union[str, Path],
    name: str = "Test World",
    level_dat_content: Union[str, bytes] = "dummy level data",
    packs: Optional[Sequence[Union[PackSpec, BuiltPack, Dict[str, Any]]]] = None,
    *,
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
) -> Path:
    """
    Creates an .mcworld file (a zip containing a world, optionally with embedded packs).
    Accepts either text or binary level_dat_content and does not mutate caller inputs.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    world_slug = sanitize_filename(name)
    mcworld_path = validate_child_path(target, f"{world_slug}.mcworld")

    built_packs = _resolve_built_packs(packs) if packs else []

    with tempfile.TemporaryDirectory() as tmpdir:
        world_dir = Path(tmpdir) / "world"
        world_dir.mkdir(parents=True, exist_ok=True)

        level_bytes = (
            level_dat_content.encode("utf-8")
            if isinstance(level_dat_content, str)
            else bytes(level_dat_content)
        )
        (world_dir / "level.dat").write_bytes(level_bytes)
        (world_dir / "levelname.txt").write_text(name, encoding="utf-8")

        if built_packs:
            bp_dir = world_dir / "behavior_packs"
            rp_dir = world_dir / "resource_packs"

            world_behavior_packs = []
            world_resource_packs = []

            for built in built_packs:
                pack_type = built.spec.pack_type
                dest_parent = bp_dir if pack_type in ("data", "script") else rp_dir
                write_pack_directory(dest_parent, built)

                if built.manifest_data is not None:
                    header = built.manifest_data.get("header", {})
                    if (
                        isinstance(header, dict)
                        and "uuid" in header
                        and "version" in header
                    ):
                        entry = {
                            "pack_id": header["uuid"],
                            "version": header["version"],
                        }
                        if pack_type in ("data", "script"):
                            world_behavior_packs.append(entry)
                        else:
                            world_resource_packs.append(entry)

            if world_behavior_packs:
                (world_dir / "world_behavior_packs.json").write_text(
                    json.dumps(world_behavior_packs, indent=4), encoding="utf-8"
                )
            if world_resource_packs:
                (world_dir / "world_resource_packs.json").write_text(
                    json.dumps(world_resource_packs, indent=4), encoding="utf-8"
                )

        if extra_files:
            for rel_path, content in extra_files.items():
                norm_rel = rel_path.replace("\\", "/").lstrip("/")
                if ".." in Path(norm_rel).parts:
                    raise ValueError(f"Unsafe extra_files path: {rel_path!r}")
                dest = world_dir / norm_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(
                    content.encode("utf-8")
                    if isinstance(content, str)
                    else bytes(content)
                )

        with zipfile.ZipFile(mcworld_path, "w", zipfile.ZIP_DEFLATED) as mcworld_zf:
            for root, _, files in os.walk(world_dir):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, world_dir).replace("\\", "/")
                    mcworld_zf.write(file_path, arcname=arcname)

    return mcworld_path


# Explicit archive/import failure fixture generators


def create_corrupt_archive(
    target_dir: Union[str, Path],
    filename: str = "corrupt.mcpack",
    mode: Literal["not_a_zip", "truncated_zip"] = "not_a_zip",
) -> Path:
    """Creates a deliberately corrupt archive for negative import/restore testing."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = validate_child_path(target, filename)

    if mode == "not_a_zip":
        dest.write_bytes(b"NOT_A_ZIP_HEADER\x00\x01\x02\x03invalid payload")
    elif mode == "truncated_zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", '{"format_version": 2}')
            zf.writestr("payload.bin", b"x" * 512)
        raw = buf.getvalue()
        dest.write_bytes(raw[: max(16, len(raw) // 2)])
    else:
        raise ValueError(f"Unknown corruption mode: {mode!r}")

    return dest


def create_traversal_archive(
    target_dir: Union[str, Path],
    filename: str = "traversal.zip",
    traversal_entry: str = "../escaped.txt",
    payload: bytes = b"escaped content",
) -> Path:
    """Creates a ZIP archive containing a path-traversal entry (ZipSlip test fixture)."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = validate_child_path(target, filename)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("safe.txt", b"safe content")
        zf.writestr(traversal_entry, payload)

    return dest


def create_duplicate_entry_archive(
    target_dir: Union[str, Path],
    filename: str = "duplicate_entries.mcpack",
    entry_name: str = "manifest.json",
) -> Path:
    """Creates a ZIP archive containing duplicate entry names."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = validate_child_path(target, filename)

    built = build_pack(PackSpec(name="Duplicate Entry Pack", pack_type="data"))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in built.files.items():
            zf.writestr(rel_path, content)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            zf.writestr(entry_name, b'{"format_version": 2, "duplicate": true}')

    return dest


def create_checksum_mismatch_archive(
    target_dir: Union[str, Path],
    filename: str = "crc_mismatch.zip",
) -> Path:
    """
    Creates a ZIP archive where a file's stored payload bytes are flipped after
    writing headers/CRC so zipfile.ZipFile.testzip() / read() detects a CRC-32 mismatch.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = validate_child_path(target, filename)

    marker = b"ORIGINAL_PAYLOAD_BYTES_FOR_CRC_CHECK"
    corrupted = b"CORRUPTED_PAYLOAD_BYTES_FOR_CRC_FAIL"
    assert len(marker) == len(corrupted)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("data.txt", marker)

    raw = buf.getvalue()
    idx = raw.find(marker)
    if idx == -1:
        raise RuntimeError("Marker payload not found in uncompressed zip buffer")
    mutated = raw[:idx] + corrupted + raw[idx + len(marker) :]
    dest.write_bytes(mutated)
    return dest
