"""Import the exact audited model and a small, documented evidence subset."""
import csv
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = PurePosixPath("ThermoCircular_Complete_Research_2026/source_material")
AUDIT = ARCHIVE_ROOT / "Audited"
MODEL = AUDIT / "Final_Engineering_Optimization_Model"
ALLOWED = {".pptx", ".png", ".pdf", ".md", ".py", ".docx", ".txt", ".html", ".xlsx", ".csv"}
MODEL_FILES = (
    "optimize.py", "legacy_engine.py", "check_model.py", "README.md",
    "example_hourly_inputs.csv", "results/scenario_results.csv",
    "results/investment_steps.csv", "results/stress_tests.csv", "results/hourly_D.csv",
)
EVIDENCE = ("Research_Master_Bibliography.csv", "Submission_Sources.csv")
SHEETS = ("Monthly", "Regional leads", "Gate evidence", "Gate status", "Score criteria", "Sources")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(relative, data):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise RuntimeError(f"Existing snapshot differs: {relative}")
    path.write_bytes(data)
    return sha(data)


def main(archive, audited_copy):
    data = {}
    with ZipFile(archive) as source:
        members = source.infolist()
        names = set()
        if len(members) > 400 or sum(info.file_size for info in members) > 150_000_000:
            raise ValueError("Unexpected archive size")
        for info in members:
            name = info.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or "\\" in name or ":" in name or ".." in path.parts
                    or name.casefold() in names or stat.S_ISLNK(info.external_attr >> 16)
                    or info.file_size > 25_000_000 or path.parts[0] != ARCHIVE_ROOT.parts[0]
                    or (not info.is_dir() and path.suffix.lower() not in ALLOWED)):
                raise ValueError(f"Unexpected archive member: {name}")
            names.add(name.casefold())
        if source.testzip() is not None:
            raise ValueError("Archive CRC failed")
        archive_members = {info.filename: sha(source.read(info)) for info in members if not info.is_dir()}
        for name in MODEL_FILES:
            content = source.read(str(MODEL / name))
            if content != (audited_copy / "Final_Engineering_Optimization_Model" / name).read_bytes():
                raise ValueError(f"Audited disk copy disagrees with archive: {name}")
            data[f"vendor/audited_model/{name}"] = put(f"vendor/audited_model/{name}", content)
        for name in EVIDENCE:
            path = f"data/evidence/{name}"
            content = source.read(str(AUDIT / "Evidence" / name)).decode("utf-8-sig")
            content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "§", content)
            data[path] = put(path, content.encode("utf-8"))
        from io import BytesIO, StringIO
        workbook = openpyxl.load_workbook(
            BytesIO(source.read(str(AUDIT / "Evidence/Austrian_Regional_Data.xlsx"))),
            read_only=True, data_only=True,
        )
        for sheet in SHEETS:
            with StringIO(newline="") as buf:
                csv.writer(buf).writerows(workbook[sheet].values)
                path = f"data/evidence/{sheet.lower().replace(' ', '_')}.csv"
                data[path] = put(path, buf.getvalue().encode("utf-8"))
        workbook.close()
        risks = source.read(str(AUDIT / "Outstanding_Assumptions_and_Risks.md")).decode("utf-8")
        with StringIO(newline="") as buf:
            writer = csv.writer(buf)
            writer.writerow(("ID", "Decision", "Status", "Verification"))
            for line in risks.splitlines():
                if re.match(r"^\| R\d{2} \|", line):
                    writer.writerow(cell.strip() for cell in line.strip("|").split("|"))
            path = "data/evidence/risks.csv"
            data[path] = put(path, buf.getvalue().encode("utf-8"))
    manifest = {"archive": Path(archive).name, "archive_sha256": sha(Path(archive).read_bytes()),
                "archive_members_sha256": archive_members, "bundled_sha256": data}
    put("data/source_manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/import_sources.py <research.zip> <independent audited directory>")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
