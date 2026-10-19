"""Bounded HTTPS download, explicit destinations, retries, conditional cache."""

import json
import os
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import requests

from .validation import sha256

BASE = "https://raw.githubusercontent.com/Kato-Shoko705/Phoebe-Hub/main/"
DEFAULT_INDEX = BASE + "data/memes.json"
ALLOWED_HOSTS = {"raw.githubusercontent.com", "kato-shoko705.github.io"}


def checked_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Disallowed source URL: {url}")
    decoded = unquote(parsed.path)
    if "\\" in decoded or any(p in (".", "..") for p in decoded.split("/")):
        raise ValueError("Unsafe source URL path")
    return url


def source_url(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Image URL must be a nonempty string")
    if value.startswith("images/"):
        value = BASE + quote(unquote(value), safe="/")
    return checked_url(value)


def atomic_bytes(path, data):
    path = Path(path)
    # Refuse symlinks even if they happen to resolve inside the cache/output.
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError(f"Symlink write target: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    if part.is_symlink():
        raise ValueError("Symlink temporary target")
    try:
        with part.open("wb") as handle:
            handle.write(data)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def write_json(path, data):
    atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


class Downloader:
    def __init__(self, cache, offline=False, refresh=False, retries=3, max_bytes=25_000_000):
        self.cache = Path(cache)
        self.offline, self.refresh = offline, refresh
        self.retries, self.max_bytes = retries, max_bytes

    def fetch(self, url):
        checked_url(url)
        key = sha256(url.encode())
        body, info = self.cache / (key + ".bin"), self.cache / (key + ".json")
        metadata = {}
        cached = None
        if body.is_file() and info.is_file() and body.stat().st_size <= self.max_bytes:
            try:
                metadata = json.loads(info.read_text("utf-8"))
                if not isinstance(metadata, dict):
                    metadata = {}
                cached = body.read_bytes()
                if sha256(cached) != metadata.get("sha256"):
                    cached, metadata = None, {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                cached, metadata = None, {}
        if cached is not None and (self.offline or not self.refresh):
            return cached
        if self.offline:
            raise ValueError(f"Offline cache miss or corruption: {url}")
        headers = {}
        if cached is not None:
            if metadata.get("etag"):
                headers["If-None-Match"] = metadata["etag"]
            if metadata.get("last_modified"):
                headers["If-Modified-Since"] = metadata["last_modified"]
        for attempt in range(self.retries + 1):
            try:
                with requests.get(
                    url, timeout=(10, 45), headers=headers, stream=True, allow_redirects=False
                ) as response:
                    if response.status_code == 304 and cached is not None:
                        return cached
                    if response.status_code in (429, 500, 502, 503, 504):
                        raise requests.ConnectionError(f"Retryable HTTP {response.status_code}")
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise ValueError(
                            f"Unexpected HTTP {response.status_code}; redirects refused"
                        )
                    data = bytearray()
                    for chunk in response.iter_content(64 * 1024):
                        data.extend(chunk)
                        if len(data) > self.max_bytes:
                            raise ValueError("Download exceeds size limit")
                    data = bytes(data)
                    atomic_bytes(body, data)
                    write_json(
                        info,
                        {
                            "sha256": sha256(data),
                            "etag": response.headers.get("ETag"),
                            "last_modified": response.headers.get("Last-Modified"),
                        },
                    )
                    return data
            except (requests.ConnectionError, requests.Timeout):
                if attempt == self.retries:
                    raise
                time.sleep(min(2**attempt, 8))
        raise RuntimeError("Unreachable")
