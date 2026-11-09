"""Local, bounded dataset discovery and safe extraction; raw files are never modified."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

EXPECTED_ZIP_SHA256 = "6d51554df43e324ba8d68fc31a02a83d860ba0a3a93d63320a4a6fc314c9cdfd"
EXPECTED_CSV_SHA1 = "2cba4879ead17c51e3268a01c06af41186cd90e4"
EXPECTED_ROWS = 2_365_424
START = "FLOW_START_MILLISECONDS"
END = "FLOW_END_MILLISECONDS"


def file_hash(path: str | Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_dataset(data_path: str | Path | None, workspace: str | Path = Path(".")) -> tuple[Path, dict]:
    workspace = Path(workspace).resolve()
    if data_path is None:
        candidates = sorted(workspace.glob("*NFV3DATA-A11964_A11964*.zip"))
        candidates += list(workspace.glob("NF-UNSW-NB15-v3.csv"))
        candidates += list((workspace / "data/raw").glob("NF-UNSW-NB15-v3.csv"))
        if not candidates:
            raise FileNotFoundError(f"No local dataset in {workspace} or {workspace / 'data/raw'}")
        source = candidates[0]
    else:
        source = Path(data_path)
        if not source.is_absolute():
            source = workspace / source
    if not source.is_file():
        raise FileNotFoundError(source)
    provenance = {"source": str(source.resolve()), "expected_zip_sha256": EXPECTED_ZIP_SHA256,
                  "expected_csv_sha1": EXPECTED_CSV_SHA1}
    if source.suffix.lower() == ".zip":
        provenance["zip_sha256"] = file_hash(source)
        if provenance["zip_sha256"] != EXPECTED_ZIP_SHA256:
            raise ValueError(f"Dataset identity mismatch: ZIP SHA256 {provenance['zip_sha256']}")
        destination = workspace / "data/raw"
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            members = []
            for member in archive.infolist():
                name = PurePosixPath(member.filename.replace("\\", "/"))
                mode = member.external_attr >> 16
                if name.is_absolute() or ".." in name.parts or ":" in member.filename or stat.S_ISLNK(mode):
                    raise ValueError(f"Unsafe archive member: {member.filename}")
                if name.name in {"NF-UNSW-NB15-v3.csv", "NetFlow_v3_Features.csv", "manifest-sha1.txt"}:
                    members.append(member)
            if len({PurePosixPath(m.filename).name for m in members}) != len(members):
                raise ValueError("Ambiguous duplicate data names in archive")
            required = sum(m.file_size for m in members)
            if shutil.disk_usage(destination).free < required + 512 * 1024**2:
                raise OSError("Insufficient free disk for safe dataset extraction")
            for member in members:
                target = destination / PurePosixPath(member.filename).name
                if not target.exists():
                    temporary = target.with_suffix(target.suffix + ".partial")
                    with archive.open(member) as incoming, temporary.open("wb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 8 * 1024 * 1024)
                    if temporary.stat().st_size != member.file_size:
                        raise ValueError("Incomplete archive extraction")
                    os.replace(temporary, target)
            source = destination / "NF-UNSW-NB15-v3.csv"
            manifest = (destination / "manifest-sha1.txt").read_text(encoding="utf-8-sig")
            manifest_lines = [line for line in manifest.splitlines() if line.rstrip().endswith("NF-UNSW-NB15-v3.csv")]
            if len(manifest_lines) != 1 or manifest_lines[0].split()[0] != EXPECTED_CSV_SHA1:
                raise ValueError("CSV manifest SHA1 does not match expected dataset")
            provenance["manifest_csv_sha1"] = manifest_lines[0].split()[0]
    provenance["csv_sha1"] = file_hash(source, "sha1")
    provenance["csv_sha256"] = file_hash(source, "sha256")
    provenance["csv_path"] = str(source.resolve())
    if provenance["csv_sha1"] != EXPECTED_CSV_SHA1:
        raise ValueError(f"Dataset identity mismatch: CSV SHA1 {provenance['csv_sha1']}")
    return source, provenance


def read_dataset(workspace: str | Path = Path("."), columns=None):
    import pandas as pd
    return pd.read_parquet(Path(workspace) / "data/processed/dataset.parquet", columns=columns)


def dataset_batches(workspace: str | Path = Path("."), columns=None, batch_size=100_000):
    import pyarrow.parquet as pq
    source = pq.ParquetFile(Path(workspace) / "data/processed/dataset.parquet")
    for batch in source.iter_batches(batch_size=batch_size, columns=columns):
        yield batch.to_pandas()
