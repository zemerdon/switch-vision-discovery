#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import argparse
import stat
import tarfile


@dataclass(frozen=True)
class Entry:
    kind: str
    mode: int
    digest: str | None


def normalize_name(name: str) -> str:
    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/")


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def source_entries(root: Path) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()

        if "__pycache__" in path.parts:
            raise RuntimeError(
                f"Forbidden Python cache directory in source: {rel}"
            )

        if path.suffix in {".pyc", ".pyo"}:
            raise RuntimeError(
                f"Forbidden Python bytecode in source: {rel}"
            )

        if path.is_symlink():
            raise RuntimeError(
                f"Symlink not permitted in runtime source: {rel}"
            )

        st = path.stat()
        mode = stat.S_IMODE(st.st_mode)

        if path.is_dir():
            entries[rel] = Entry(
                kind="dir",
                mode=mode,
                digest=None,
            )
        elif path.is_file():
            entries[rel] = Entry(
                kind="file",
                mode=mode,
                digest=digest_bytes(path.read_bytes()),
            )
        else:
            raise RuntimeError(
                f"Unsupported filesystem entry in source: {rel}"
            )

    return entries


def archive_entries(path: Path) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}

    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = normalize_name(member.name)

            # A tar may contain an explicit "." root entry.
            if not name or name == ".":
                continue

            p = PurePosixPath(name)

            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError(
                    f"Unsafe archive path: {member.name}"
                )

            if "__pycache__" in p.parts:
                raise RuntimeError(
                    f"Forbidden Python cache in archive: {member.name}"
                )

            if p.suffix in {".pyc", ".pyo"}:
                raise RuntimeError(
                    f"Forbidden Python bytecode in archive: {member.name}"
                )

            if member.issym() or member.islnk():
                raise RuntimeError(
                    f"Link not permitted in runtime archive: {member.name}"
                )

            if member.isdev() or member.isfifo():
                raise RuntimeError(
                    f"Special entry not permitted in runtime archive: {member.name}"
                )

            mode = member.mode & 0o7777

            if member.isdir():
                entries[name] = Entry(
                    kind="dir",
                    mode=mode,
                    digest=None,
                )
                continue

            if not member.isfile():
                raise RuntimeError(
                    f"Unsupported archive entry: {member.name}"
                )

            extracted = archive.extractfile(member)

            if extracted is None:
                raise RuntimeError(
                    f"Unable to read archive file: {member.name}"
                )

            entries[name] = Entry(
                kind="file",
                mode=mode,
                digest=digest_bytes(extracted.read()),
            )

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that runtime_src and runtime.tar.gz contain "
            "the same runtime tree."
        )
    )

    parser.add_argument(
        "--source",
        default="runtime_src",
    )

    parser.add_argument(
        "--archive",
        default="switch_vision_discovery/runtime.tar.gz",
    )

    args = parser.parse_args()

    source = Path(args.source)
    archive = Path(args.archive)

    if not source.is_dir():
        raise SystemExit(
            f"ERROR: runtime source directory not found: {source}"
        )

    if not archive.is_file():
        raise SystemExit(
            f"ERROR: runtime archive not found: {archive}"
        )

    src = source_entries(source)
    arc = archive_entries(archive)

    src_names = set(src)
    arc_names = set(arc)

    errors: list[str] = []

    only_source = sorted(src_names - arc_names)
    only_archive = sorted(arc_names - src_names)

    for name in only_source:
        errors.append(
            f"Only in runtime source: {name}"
        )

    for name in only_archive:
        errors.append(
            f"Only in runtime archive: {name}"
        )

    for name in sorted(src_names & arc_names):
        left = src[name]
        right = arc[name]

        if left.kind != right.kind:
            errors.append(
                f"Type mismatch for {name}: "
                f"source={left.kind}, archive={right.kind}"
            )
            continue

        if left.mode != right.mode:
            errors.append(
                f"Mode mismatch for {name}: "
                f"source={left.mode:04o}, archive={right.mode:04o}"
            )

        if left.digest != right.digest:
            errors.append(
                f"Content mismatch for {name}: "
                f"source={left.digest}, archive={right.digest}"
            )

    if errors:
        print("Discovery runtime source/archive parity: FAIL")

        for error in errors:
            print(f"ERROR: {error}")

        return 1

    file_count = sum(
        1 for entry in src.values()
        if entry.kind == "file"
    )

    dir_count = sum(
        1 for entry in src.values()
        if entry.kind == "dir"
    )

    print(
        "Discovery runtime source/archive parity: PASS "
        f"({file_count} files, {dir_count} directories)"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
