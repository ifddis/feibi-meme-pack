"""Build an allowlisted, deterministic ZIP and adjacent SHA-256 file (stdlib only)."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import zipfile


def build(source, output, files):
    root = Path(source).resolve(strict=True)
    target = Path(output).resolve()
    entries = {}
    for name in files:
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
            raise ValueError(f'Unsafe archive path: {name}')
        path = root.joinpath(*rel.parts)
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError(f'Symlink not allowed: {name}')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file() or resolved == target:
            raise ValueError(f'Expected source file inside source root: {name}')
        if rel.as_posix() in entries:
            raise ValueError(f'Duplicate entry: {name}')
        entries[rel.as_posix()] = resolved.read_bytes()
    if not entries:
        raise ValueError('Explicit nonempty file allowlist required')
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(entries):
            raise ValueError('ZIP verification failed')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix + '.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    return digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    print(build(args.source, args.output, args.files))
