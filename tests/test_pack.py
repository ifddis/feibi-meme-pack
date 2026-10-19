import hashlib
import io
import json
from pathlib import Path

import pytest
import requests
from jsonschema import ValidationError
from PIL import Image

from feibi_pack.builder import build, parse_index
from feibi_pack.download import BASE, Downloader, source_url, write_json
from feibi_pack.semantics import classify
from feibi_pack.validation import entry_id, safe_path, sha256, validate_pack


def image_bytes(fmt="PNG", color="red", animated=False):
    result = io.BytesIO()
    a = Image.new("RGB", (3, 3), color)
    if animated:
        a.save(
            result,
            format=fmt,
            save_all=True,
            append_images=[Image.new("RGB", (3, 3), "blue")],
            duration=80,
            loop=0,
        )
    else:
        a.save(result, format=fmt)
    return result.getvalue()


def index_file(tmp_path, records):
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"memes": records, "pending": [{"url": "evil"}]}), "utf-8")
    return path


def record(title, url="images/test.png", tags=None):
    return {"title": title, "url": url, "tags": tags or []}


def seed(cache, url, data):
    key = sha256(source_url(url).encode())
    cache.mkdir(exist_ok=True)
    (cache / (key + ".bin")).write_bytes(data)
    write_json(cache / (key + ".json"), {"sha256": sha256(data), "etag": '"v1"'})


@pytest.mark.parametrize(
    "word,category",
    [
        ("哈气", "hissing"),
        ("菲比乱拳", "punching"),
        ("生气", "angry"),
        ("吃蛋糕", "cake"),
        ("开心", "happy"),
        ("委屈", "aggrieved"),
        ("害羞", "shy"),
        ("跳舞", "dancing"),
        ("我不能哈气了", "review"),
        ("开心但生气", "review"),
        ("cute", "review"),
        ("蛋糕", "review"),
    ],
)
def test_classification(word, category):
    assert classify(record(word))[0] == category


def test_tags_filename():
    assert classify(record("菲比", "images/跳舞.gif"))[0] == "dancing"
    assert classify(record("菲比", tags=["委屈"]))[0] == "aggrieved"


@pytest.mark.parametrize(
    "path", ["../escape", "/tmp/a", "memes/../../a", "a\\b", "C:/a", "a//b", "a/./b"]
)
def test_unsafe_paths(tmp_path, path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


@pytest.mark.parametrize(
    "url",
    [
        "http://raw.githubusercontent.com/a",
        "https://evil.test/x",
        "//evil.test/a",
        "images/../a.png",
        "images/%2e%2e/a.png",
        "https://raw.githubusercontent.com:444/a",
        "https://user@raw.githubusercontent.com/a",
    ],
)
def test_unsafe_urls(url):
    with pytest.raises(ValueError):
        source_url(url)


def test_upstream_shape_and_pending():
    assert len(parse_index({"memes": [record("开心")], "pending": [None]})) == 1
    for value in [[], {"memes": [record("a", tags=[1])]}, {"memes": [{}]}]:
        with pytest.raises(ValueError):
            parse_index(value)


def test_identity_independent_formula():
    digest = "a" * 64
    assert (
        entry_id(digest, "happy", "memes/happy/a.png")
        == hashlib.sha256(digest.encode() + b"\x00happy\x00memes/happy/a.png").hexdigest()
    )


def test_build_dedupe_gif_review_and_incremental(tmp_path):
    cache = tmp_path / "cache"
    data = image_bytes("GIF", animated=True)
    seed(cache, "images/a.gif", data)
    seed(cache, "images/b.gif", data)
    seed(cache, "images/c.png", image_bytes(color="green"))
    index = index_file(
        tmp_path,
        [
            record("哈气", "images/a.gif"),
            record("哈气比", "images/b.gif"),
            record("unknown", "images/c.png"),
        ],
    )
    out = tmp_path / "pack"
    result = build(index, out, cache, offline=True)
    assert result["images"] == 1
    assert result["review_pending"] == 1
    files = list((out / "memes").glob("*/*"))
    assert files[0].read_bytes() == data
    with Image.open(files[0]) as image:
        assert image.n_frames == 2
    assert validate_pack(out, require_complete=True)["images"] == 1
    repeat = tmp_path / "repeat"
    build(index, repeat, cache, offline=True)
    for name in ["manifest.json", "semantic_metadata.json", "provenance.json"]:
        assert (out / name).read_bytes() == (repeat / name).read_bytes()
    with pytest.raises(ValueError, match="exists"):
        build(index, out, cache, offline=True)
    metadata = json.loads((out / "semantic_metadata.json").read_text("utf-8"))
    assert next(iter(metadata["images"].values()))["caption_status"] == "pending"
    files[0].write_bytes(image_bytes("GIF", color="green"))
    with pytest.raises(ValueError, match="Identity"):
        validate_pack(out)


def test_conflicting_duplicate_and_human_override(tmp_path):
    cache = tmp_path / "cache"
    data = image_bytes()
    seed(cache, "images/a.png", data)
    index = index_file(tmp_path, [record("开心", "images/a.png"), record("生气", "images/a.png")])
    out = tmp_path / "pack"
    result = build(index, out, cache, offline=True, include_review=True)
    assert result["review_pending"] == 1
    meta = json.loads((out / "semantic_metadata.json").read_text("utf-8"))
    assert next(iter(meta["images"].values()))["category"] == "review"
    override = {sha256(data): {"category": "happy", "caption": "人工确认：菲比开心微笑。"}}
    build(index, tmp_path / "reviewed", cache, offline=True, overrides=override)
    meta = json.loads((tmp_path / "reviewed/semantic_metadata.json").read_text("utf-8"))
    assert next(iter(meta["images"].values()))["caption_status"] == "done"


def test_corrupt_offline_cache(tmp_path):
    seed(tmp_path, "images/test.png", image_bytes())
    next(tmp_path.glob("*.bin")).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="cache"):
        Downloader(tmp_path, offline=True).fetch(BASE + "images/test.png")


class Response:
    def __init__(self, status=200, content=b"hello", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        yield self.content


def test_retry_conditional_and_size_limit(tmp_path, monkeypatch):
    replies = iter([Response(503), Response(200, headers={"ETag": '"v1"'}), Response(304)])
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return next(replies)

    monkeypatch.setattr("feibi_pack.download.requests.get", get)
    monkeypatch.setattr("feibi_pack.download.time.sleep", lambda _: None)
    download = Downloader(tmp_path, refresh=True)
    url = BASE + "images/test.png"
    assert download.fetch(url) == b"hello"
    assert download.fetch(url) == b"hello"
    assert calls[-1]["headers"]["If-None-Match"] == '"v1"'
    assert calls[0]["allow_redirects"] is False
    monkeypatch.setattr(
        "feibi_pack.download.requests.get", lambda *a, **k: Response(content=b"1234")
    )
    with pytest.raises(ValueError, match="size"):
        Downloader(tmp_path / "small", max_bytes=3).fetch(url)
    assert not list((tmp_path / "small").glob("*.bin"))


def test_redirect_and_permanent_failure(tmp_path, monkeypatch):
    for status, error in [(302, ValueError), (404, requests.HTTPError)]:
        monkeypatch.setattr(
            "feibi_pack.download.requests.get", lambda *a, status=status, **k: Response(status)
        )
        with pytest.raises(error):
            Downloader(tmp_path).fetch(BASE + "images/test.png")


def test_invalid_image_does_not_publish_output(tmp_path):
    seed(tmp_path / "cache", "images/test.png", b"not an image")
    index = index_file(tmp_path, [record("开心")])
    with pytest.raises(OSError):
        build(index, tmp_path / "pack", tmp_path / "cache", offline=True)
    assert not (tmp_path / "pack").exists()
    assert not list(tmp_path.glob(".feibi-stage-*"))


def test_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable on this host")
    with pytest.raises(ValueError):
        safe_path(root, "escape/private")


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_formats_preserved(tmp_path, fmt):
    data = image_bytes(fmt)
    cache = tmp_path / "cache"
    seed(cache, "images/test.png", data)
    index = index_file(tmp_path, [record("开心")])
    build(index, tmp_path / "pack", cache, offline=True)
    target = next((tmp_path / "pack/memes/happy").iterdir())
    assert target.read_bytes() == data
    assert validate_pack(tmp_path / "pack", True)["images"] == 1


@pytest.mark.parametrize(
    "mutation", ["pack_id", "entry_id", "category", "missing_file", "missing_record", "schema"]
)
def test_validator_rejects_invalid_associations(tmp_path, mutation):
    cache = tmp_path / "cache"
    seed(cache, "images/test.png", image_bytes())
    index = index_file(tmp_path, [record("开心")])
    out = tmp_path / "pack"
    build(index, out, cache, offline=True)
    semantic_path = out / "semantic_metadata.json"
    semantic = json.loads(semantic_path.read_text("utf-8"))
    item = next(iter(semantic["images"].values()))
    if mutation == "pack_id":
        semantic["pack_id"] = "wrong-id"
    elif mutation == "entry_id":
        item["entry_id"] = "a" * 64
    elif mutation == "category":
        item["category"] = "angry"
    elif mutation == "missing_file":
        (out / item["relative_path"]).unlink()
    elif mutation == "missing_record":
        semantic["images"] = {}
    else:
        semantic["schema_version"] = "1.0"
    write_json(semantic_path, semantic)
    with pytest.raises((ValueError, ValidationError)):
        validate_pack(out, require_complete=True)


def test_validator_rejects_memes_symlink_to_other_pack_directory(tmp_path):
    cache = tmp_path / "cache"
    seed(cache, "images/test.png", image_bytes())
    index = index_file(tmp_path, [record("开心")])
    out = tmp_path / "pack"
    build(index, out, cache, offline=True)
    category = out / "memes/happy"
    moved = out / "other"
    category.rename(moved)
    try:
        category.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable on this host")
    with pytest.raises(ValueError, match="escapes memes"):
        validate_pack(out)


def test_basic_protocol_allows_partial_semantics(tmp_path):
    cache = tmp_path / "cache"
    seed(cache, "images/test.png", image_bytes())
    index = index_file(tmp_path, [record("开心")])
    out = tmp_path / "pack"
    build(index, out, cache, offline=True)
    metadata = json.loads((out / "semantic_metadata.json").read_text("utf-8"))
    metadata["images"] = {}
    write_json(out / "semantic_metadata.json", metadata)
    assert validate_pack(out)["semantic_records"] == 0
    with pytest.raises(ValueError, match="cover"):
        validate_pack(out, require_complete=True)
    (out / "semantic_metadata.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        validate_pack(out)
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    del manifest["extensions"]
    write_json(out / "manifest.json", manifest)
    assert validate_pack(out)["semantic"] is False


def test_output_and_cache_guards(tmp_path):
    cache = tmp_path / "cache"
    index = index_file(tmp_path, [])
    with pytest.raises(ValueError, match="Cache"):
        build(index, tmp_path / "pack", tmp_path / "pack/cache")
    with pytest.raises(ValueError, match="workers"):
        build(index, tmp_path / "pack", cache, workers=100)
    with pytest.raises(ValueError, match="checkout"):
        build(index, Path(__file__).resolve().parents[1], cache)


def test_empty_pack_has_review_directory(tmp_path):
    index = index_file(tmp_path, [])
    result = build(index, tmp_path / "pack", tmp_path / "cache", offline=True)
    assert result["usable_images"] == 0
    assert (tmp_path / "pack/memes/review").is_dir()


def test_malformed_cache_metadata_recovers_online(tmp_path, monkeypatch):
    seed(tmp_path, "images/test.png", b"old")
    next(tmp_path.glob("*.json")).write_text("{broken", "utf-8")
    monkeypatch.setattr(
        "feibi_pack.download.requests.get", lambda *a, **k: Response(content=b"new")
    )
    assert Downloader(tmp_path).fetch(BASE + "images/test.png") == b"new"
    assert Downloader(tmp_path, offline=True).fetch(BASE + "images/test.png") == b"new"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("菲比哭哭", "aggrieved"),
        ("呜呜呜", "aggrieved"),
        ("气鼓鼓菲比", "angry"),
        ("小拳拳菲比", "punching"),
        ("菲比左勾拳", "punching"),
        ("不好意思", "shy"),
        ("不好意柿", "shy"),
        ("菲比扭扭跳跳", "dancing"),
        ("菲比炫面", "eating"),
        ("干饭菲比_1", "eating"),
        ("菲比比心", "affection"),
        ("视频点头菲比", "approval"),
        ("NO！NO！", "refusal"),
        ("？菲比", "confused"),
        ("牌没问题", "gaming"),
        ("菲比舞枪", "combat"),
        ("不许睡觉", "waking"),
        ("菲比睡觉不老实", "sleeping"),
        ("我不开心", "review"),
        ("没有跳舞", "review"),
        ("吃大福菲比", "eating"),
        ("未命名1", "review"),
        ("猫和老鼠系列10", "review"),
        ("菲比", "review"),
        ("打麻将哈哈", "gaming"),
        ("异色哈哈", "review"),
    ],
)
def test_meaningful_name_regressions(title, expected):
    assert classify(record(title, "images/opaque-identifier.gif"))[0] == expected


def test_partial_download_requires_explicit_opt_in(tmp_path, monkeypatch):
    index = index_file(tmp_path, [record("哭哭", "images/missing.gif"), record("干饭")])

    def fetch(self, url):
        if "missing" in url:
            raise requests.HTTPError("404 not found")
        seed(self.cache, "images/test.png", image_bytes())
        return image_bytes()

    monkeypatch.setattr("feibi_pack.builder.Downloader.fetch", fetch)
    with pytest.raises(requests.HTTPError):
        build(index, tmp_path / "strict", tmp_path / "cache")
    out = tmp_path / "partial"
    result = build(index, out, tmp_path / "cache", skip_failed=True, complete_name_captions=True)
    assert result["failed_assets"] == 1
    assert result["images"] == 1
    failures = json.loads((out / "download_failures.json").read_text("utf-8"))
    assert failures[0]["stage"] == "download"
    meta = json.loads((out / "semantic_metadata.json").read_text("utf-8"))
    image = next(iter(meta["images"].values()))
    assert image["category"] == "eating"
    assert image["caption_status"] == "done"
    assert "名称" in image["provenance"] or "标题" in image["provenance"]
    assert validate_pack(out, True)["images"] == 1


def test_invalid_image_is_reported_with_opt_in(tmp_path):
    cache = tmp_path / "cache"
    seed(cache, "images/test.png", b"not an image")
    index = index_file(tmp_path, [record("开心")])
    result = build(index, tmp_path / "pack", cache, offline=True, skip_failed=True)
    assert result["images"] == 0 and result["failed_assets"] == 1
    failures = json.loads((tmp_path / "pack/download_failures.json").read_text("utf-8"))
    assert failures[0]["stage"] == "image-validation"
