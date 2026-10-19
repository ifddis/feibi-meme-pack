"""Official JSON Schema plus filesystem, image and identity validation."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
FORMATS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def entry_id(content_hash, category, path):
    return sha256(f"{content_hash}\0{category}\0{path}".encode())


def safe_path(root, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
        or ".." in relative
        or "\x00" in relative
    ):
        raise ValueError(f"Unsafe path: {relative!r}")
    p = PurePosixPath(relative)
    if p.is_absolute() or any(x in ("", ".", "..") for x in relative.split("/")):
        raise ValueError(f"Unsafe path: {relative!r}")
    root = Path(root).resolve()
    target = root.joinpath(*p.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError(f"Path escapes root: {relative}")
    return target


def image_format(path):
    with Image.open(path) as image:
        fmt = image.format
        image.verify()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported image format: {fmt}")
    return FORMATS[fmt]


def validate_schema(data, name):
    schema = json.loads((SCHEMAS / f"meme-pack-{name}.schema.json").read_text("utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)


def validate_pack(root, require_complete=False):
    root = Path(root).resolve()
    manifest = json.loads(safe_path(root, "manifest.json").read_text("utf-8"))
    validate_schema(manifest, "manifest")
    memes = safe_path(root, "memes")
    if not memes.is_dir():
        raise ValueError("Missing memes directory")
    files = set()
    for category in memes.iterdir():
        if category.name not in manifest["categories"] or not category.is_dir():
            raise ValueError(f"Undeclared category or unexpected file: {category.name}")
        safe_path(root, category.relative_to(root).as_posix())
        for image in category.iterdir():
            relative = image.relative_to(root).as_posix()
            path = safe_path(root, relative)
            if not path.resolve().is_relative_to(memes.resolve()):
                raise ValueError(f"Image escapes memes directory: {relative}")
            if not path.is_file():
                raise ValueError(f"Image must be a file: {relative}")
            ext = image_format(path)
            if path.suffix.lower() not in ({".jpg", ".jpeg"} if ext == ".jpg" else {ext}):
                raise ValueError(f"Image extension mismatch: {relative}")
            files.add(relative)
    for relative in [
        *manifest.get("previews", []),
        *([manifest["icon"]] if "icon" in manifest else []),
    ]:
        path = safe_path(root, relative)
        ext = image_format(path)
        if path.suffix.lower() not in ({".jpg", ".jpeg"} if ext == ".jpg" else {ext}):
            raise ValueError(f"Preview extension mismatch: {relative}")
    semantic_path = safe_path(root, "semantic_metadata.json")
    declared = "semantic" in manifest.get("extensions", {})
    if declared and not semantic_path.is_file():
        raise ValueError("Declared semantic metadata missing")
    covered = set()
    if semantic_path.exists():
        semantic = json.loads(semantic_path.read_text("utf-8"))
        validate_schema(semantic, "semantic")
        if semantic["pack_id"] != manifest["id"]:
            raise ValueError("Semantic pack_id mismatch")
        for key, record in semantic["images"].items():
            relative, category = record["relative_path"], record["category"]
            path = safe_path(root, relative)
            if (
                relative not in files
                or len(PurePosixPath(relative).parts) != 3
                or PurePosixPath(relative).parts[1] != category
                or category not in manifest["categories"]
                or relative in covered
            ):
                raise ValueError(f"Invalid semantic association: {relative}")
            digest = sha256(path.read_bytes())
            identity = entry_id(digest, category, relative)
            if digest != record["content_sha256"] or key != identity or record["entry_id"] != key:
                raise ValueError(f"Identity mismatch: {relative}")
            covered.add(relative)
    if require_complete and files != covered:
        raise ValueError("Semantic metadata must cover every image")
    return {
        "images": len(files),
        "semantic_records": len(covered),
        "semantic": semantic_path.exists(),
    }
