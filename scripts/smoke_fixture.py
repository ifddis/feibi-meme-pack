"""Generate original test images and run the real CLI offline (no third-party assets)."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from feibi_pack.download import source_url, write_json  # noqa: E402
from feibi_pack.validation import sha256  # noqa: E402
from PIL import Image  # noqa: E402


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cache = root / "cache"
        cache.mkdir()
        url = source_url("images/test.gif")
        image_path = cache / (sha256(url.encode()) + ".bin")
        Image.new("RGB", (4, 4), "red").save(
            image_path,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (4, 4), "blue")],
            duration=100,
            loop=0,
        )
        write_json(image_path.with_suffix(".json"), {"sha256": sha256(image_path.read_bytes())})
        index = root / "index.json"
        write_json(index, {"memes": [{"title": "哈气", "url": "images/test.gif", "tags": []}]})
        subprocess.run(
            [
                sys.executable,
                str(repo / "scripts/build_pack.py"),
                "--index",
                str(index),
                "--cache",
                str(cache),
                "--output",
                str(root / "pack"),
                "--offline",
            ],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(repo / "scripts/validate_pack.py"),
                str(root / "pack"),
                "--require-complete",
            ],
            cwd=repo,
            check=True,
        )


if __name__ == "__main__":
    main()
