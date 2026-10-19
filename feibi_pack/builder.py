"""Deterministic content pack assembly; output stays local and ignored."""

import io
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .download import DEFAULT_INDEX, Downloader, source_url, write_json
from .semantics import CATEGORIES, classify
from .validation import FORMATS, entry_id, sha256, validate_pack


def parse_index(data):
    if not isinstance(data, dict) or not isinstance(data.get("memes"), list):
        raise ValueError("Expected Phoebe-Hub object with memes array; pending is excluded")
    result = []
    for item in data["memes"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("title", ""), str)
            or not isinstance(item.get("tags", []), list)
            or not all(isinstance(tag, str) for tag in item.get("tags", []))
        ):
            raise ValueError("Invalid meme record")
        result.append({**item, "url": source_url(item.get("url"))})
    return result


def build(
    index,
    output,
    cache,
    *,
    limit=None,
    workers=6,
    offline=False,
    refresh=False,
    include_review=False,
    version="0.1.0",
    overrides=None,
):
    if workers < 1 or workers > 32 or (limit is not None and limit < 1):
        raise ValueError("workers must be 1..32 and limit must be positive")
    raw_output = Path(output).absolute()
    if raw_output.is_symlink() or any(p.is_symlink() for p in raw_output.parents):
        raise ValueError("Output must not use symlinks")
    output = raw_output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if output == repo or output in repo.parents:
        raise ValueError("Output cannot replace the checkout or its parents")
    if output.exists():
        raise ValueError("Output exists; choose a new output directory (never overwritten)")
    cache = Path(cache).resolve()
    if cache == output or cache.is_relative_to(output):
        raise ValueError("Cache must be outside the output")
    download = Downloader(cache, offline=offline, refresh=refresh)
    source = (
        json.loads(Path(index).read_text("utf-8"))
        if index
        else json.loads(download.fetch(DEFAULT_INDEX))
    )
    items = parse_index(source)
    if limit:
        items = items[:limit]
    overrides = overrides or {}
    if not isinstance(overrides, dict):
        raise ValueError("Overrides must be an object keyed by SHA-256")
    for digest, override in overrides.items():
        if (
            len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or not isinstance(override, dict)
            or override.get("category") not in CATEGORIES
            or not isinstance(override.get("caption"), str)
            or not override["caption"].strip()
        ):
            raise ValueError("Override requires content hash, known category and nonblank caption")
    urls = list(dict.fromkeys(item["url"] for item in items))

    def fetch_to_cache(url):
        data = download.fetch(url)
        return sha256(data), cache / (sha256(url.encode()) + ".bin")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        downloaded = dict(zip(urls, pool.map(fetch_to_cache, urls), strict=True))
    # Merge metadata before classification to flag contradictory duplicate titles.
    grouped = {}
    for item in items:
        digest, _ = downloaded[item["url"]]
        grouped.setdefault(digest, []).append(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".feibi-stage-", dir=output.parent))
    try:
        (stage / "memes").mkdir()
        records, reviews, provenance, categories = {}, [], [], set()
        for digest, aliases in sorted(grouped.items()):
            item = aliases[0]
            _, cached_path = downloaded[item["url"]]
            data = cached_path.read_bytes()
            if sha256(data) != digest:
                raise ValueError("Cached image changed during build")
            with Image.open(io.BytesIO(data)) as image:
                fmt = image.format
                image.verify()
            if fmt not in FORMATS:
                raise ValueError(f"Unsupported image: {fmt}")
            results = [classify(alias) for alias in aliases]
            category, caption, _ = results[0]
            if len({r[0] for r in results}) != 1:
                category, caption = "review", ""
            human = digest in overrides
            if human:
                category, caption = overrides[digest]["category"], overrides[digest]["caption"]
            details = {
                "content_sha256": digest,
                "sources": aliases,
                "category": category,
                "caption": caption,
                "reviewed": human,
            }
            provenance.append(details)
            if category == "review":
                reviews.append(details)
                if not include_review:
                    continue
            categories.add(category)
            relative = f"memes/{category}/{digest}{FORMATS[fmt]}"
            target = stage / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)  # Preserve original bytes and all animation frames.
            identity = entry_id(digest, category, relative)
            records[identity] = {
                "entry_id": identity,
                "content_sha256": digest,
                "relative_path": relative,
                "category": category,
                "caption": caption,
                "caption_status": "done" if human and category != "review" else "pending",
                "tags": sorted({tag for alias in aliases for tag in alias.get("tags", [])}),
                "provenance": "人工覆盖" if human else "标题、文件名和标签规则推断；未视觉核验",
            }
        # A schema-valid empty review category is not claimed as a usable image pack.
        manifest = {
            "schema_version": 1,
            "id": "ifddis.feibi-chibi",
            "name": "菲比丘比",
            "version": version,
            "description": "本地构建；图片许可及语义仍需人工审核。",
            "license": "Third-party images: rights not cleared; see RIGHTS.md",
            "categories": {
                c: {"description": CATEGORIES[c]} for c in sorted(categories or {"review"})
            },
            "extensions": {"semantic": {"version": 1, "file": "semantic_metadata.json"}},
        }
        for category in manifest["categories"]:
            (stage / "memes" / category).mkdir(exist_ok=True)
        write_json(stage / "manifest.json", manifest)
        write_json(
            stage / "semantic_metadata.json",
            {"schema_version": "2.0", "pack_id": manifest["id"], "images": records},
        )
        write_json(stage / "review_queue.json", reviews)
        write_json(stage / "provenance.json", provenance)
        (stage / "RIGHTS.md").write_text(
            "# 素材许可待核实\n上游公开可访问不代表获得再分发授权。\n"
            "仅用于本地审核；没有许可证明前不要上传、公开分发或发布构件。\n"
            "来源：https://github.com/Kato-Shoko705/Phoebe-Hub\n",
            "utf-8",
        )
        result = validate_pack(stage, require_complete=True)
        if output.exists():
            raise ValueError("Output appeared during build; refusing replacement")
        stage.rename(output)
        return {
            **result,
            "review_pending": len(reviews),
            "source_records": len(items),
            "unique_downloads": len(urls),
            "unique_contents": len(grouped),
            "usable_images": len(records),
            "output": str(output),
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage)
