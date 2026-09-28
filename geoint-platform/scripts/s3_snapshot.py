#!/usr/bin/env python3
"""Protocol-level S3 snapshot and probe operations for Geto DR."""

from __future__ import annotations

import argparse
import sys
from io import BytesIO
from pathlib import Path, PurePosixPath

from app.infrastructure.s3_client import create_s3_client, ensure_bucket


def _buckets(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("at least one S3 bucket is required")
    return values


def _safe_object_path(root: Path, bucket: str, key: str) -> Path:
    bucket_path = PurePosixPath(bucket)
    key_path = PurePosixPath(key)
    if (
        bucket_path.is_absolute()
        or key_path.is_absolute()
        or ".." in bucket_path.parts
        or ".." in key_path.parts
    ):
        raise ValueError(f"unsafe S3 snapshot path: bucket={bucket!r} key={key!r}")
    target = root.joinpath(*bucket_path.parts, *key_path.parts).resolve()
    base = root.resolve()
    if target != base and base not in target.parents:
        raise ValueError("S3 snapshot path escaped backup root")
    return target


def _read_object(client, bucket: str, key: str) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def export_snapshot(root: Path, buckets: list[str]) -> int:
    client = create_s3_client()
    count = 0
    root.mkdir(parents=True, exist_ok=True)
    for bucket in buckets:
        if not client.bucket_exists(bucket):
            raise RuntimeError(f"S3 bucket does not exist: {bucket}")
        (root / bucket).mkdir(parents=True, exist_ok=True)
        for obj in client.list_objects(bucket, recursive=True):
            key = obj.object_name or ""
            if not key:
                continue
            target = _safe_object_path(root, bucket, key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_read_object(client, bucket, key))
            count += 1
    return count


def import_snapshot(root: Path, *, replace: bool) -> int:
    client = create_s3_client()
    count = 0
    if not root.is_dir():
        raise RuntimeError(f"S3 snapshot directory does not exist: {root}")

    for bucket_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        bucket = bucket_dir.name
        ensure_bucket(client, bucket, allow_create=True)
        desired: set[str] = set()

        for path in sorted(item for item in bucket_dir.rglob("*") if item.is_file()):
            key = path.relative_to(bucket_dir).as_posix()
            desired.add(key)
            with path.open("rb") as stream:
                client.put_object(
                    bucket,
                    key,
                    stream,
                    length=path.stat().st_size,
                    content_type="application/octet-stream",
                )
            count += 1

        if replace:
            existing = {
                obj.object_name
                for obj in client.list_objects(bucket, recursive=True)
                if obj.object_name
            }
            for key in sorted(existing - desired):
                client.remove_object(bucket, key)

    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure")
    ensure.add_argument("--bucket", required=True)

    export = sub.add_parser("export")
    export.add_argument("--root", required=True)
    export.add_argument("--buckets", required=True)

    restore = sub.add_parser("import")
    restore.add_argument("--root", required=True)
    restore.add_argument("--replace", action="store_true")

    put = sub.add_parser("put")
    put.add_argument("--bucket", required=True)
    put.add_argument("--key", required=True)

    get = sub.add_parser("get")
    get.add_argument("--bucket", required=True)
    get.add_argument("--key", required=True)

    delete = sub.add_parser("delete")
    delete.add_argument("--bucket", required=True)
    delete.add_argument("--key", required=True)

    args = parser.parse_args()
    client = create_s3_client()

    if args.command == "ensure":
        ensure_bucket(client, args.bucket, allow_create=True)
        return 0
    if args.command == "export":
        count = export_snapshot(Path(args.root), _buckets(args.buckets))
        print(f"exported_objects={count}")
        return 0
    if args.command == "import":
        count = import_snapshot(Path(args.root), replace=args.replace)
        print(f"imported_objects={count}")
        return 0
    if args.command == "put":
        data = sys.stdin.buffer.read()
        ensure_bucket(client, args.bucket, allow_create=True)
        client.put_object(
            args.bucket,
            args.key,
            BytesIO(data),
            length=len(data),
            content_type="application/octet-stream",
        )
        return 0
    if args.command == "get":
        sys.stdout.buffer.write(_read_object(client, args.bucket, args.key))
        return 0
    if args.command == "delete":
        client.remove_object(args.bucket, args.key)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
