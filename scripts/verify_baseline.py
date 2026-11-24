"""Run the original audit CLI in scratch and compare every archived cell."""
import csv
import json
import hashlib
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "vendor/audited_model"


def compare_csv(actual, expected):
    with actual.open(encoding="utf-8", newline="") as actual_file, expected.open(
        encoding="utf-8", newline=""
    ) as expected_file:
        output = csv.reader(actual_file)
        golden = csv.reader(expected_file)
        header = next(golden)
        assert next(output) == header, expected
        count = 0
        for count, (new, old) in enumerate(zip(output, golden, strict=True), start=1):
            assert len(new) == len(old) == len(header), (expected.name, count)
            for field, got, want in zip(header, new, old, strict=True):
                if got == want:
                    continue
                try:
                    matches = math.isclose(float(got), float(want), rel_tol=0, abs_tol=1e-6)
                except ValueError:
                    matches = False
                assert matches, (expected.name, count, field, got, want)
        return count


def main():
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    for path, expected in manifest["bundled_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="thermocircular-audit-") as temp:
        work = Path(temp)
        for script in ("optimize.py", "legacy_engine.py", "check_model.py"):
            shutil.copy2(AUDIT / script, work / script)
        env = {**os.environ, "PYTHONUTF8": "1"}
        subprocess.run([sys.executable, "optimize.py", "--out", "reproduced"], cwd=work, env=env, check=True)
        subprocess.run([sys.executable, "check_model.py", "--results", "reproduced"], cwd=work, env=env, check=True)
        for expected in sorted((AUDIT / "results").glob("*.csv")):
            count = compare_csv(work / "reproduced" / expected.name, expected)
            print(f"{expected.name}: {count:,} rows matched")
    print(f"Verified {len(manifest['bundled_sha256'])} bundled hashes and four CSVs in {time.perf_counter() - started:.2f} s.")


if __name__ == "__main__":
    main()
