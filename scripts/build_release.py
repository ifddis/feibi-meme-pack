"""Build a deterministic production ZIP with no test SDK or local data."""

import ast
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from astrbot_plugin_random_events.engine import Settings  # noqa: E402

FILES = [
    "__init__.py",
    "main.py",
    "engine.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "VALIDATION.md",
]


def main():
    metadata = yaml.safe_load((ROOT / "metadata.yaml").read_text("utf-8"))
    for key in ("name", "desc", "version", "author"):
        assert isinstance(metadata.get(key), str) and metadata[key].strip(), key
    schema = json.loads((ROOT / "_conf_schema.json").read_text("utf-8"))
    Settings.from_config({key: value["default"] for key, value in schema.items()})
    target = ROOT.parent / f"{metadata['name']}-{metadata['version']}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            path = ROOT / name
            assert path.is_file() and not path.is_symlink()
            content = path.read_bytes()
            if name.endswith(".py"):
                ast.parse(content.decode("utf-8"), filename=name)
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, content)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == sorted(FILES)
        assert all(
            not Path(name).is_absolute() and ".." not in Path(name).parts
            for name in archive.namelist()
        )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", "utf-8")
    print(f"Built {target.name}: {target.stat().st_size} bytes; ZIP integrity passed")
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
