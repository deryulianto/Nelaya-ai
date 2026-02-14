# di scripts/download_latest_available.py
import os
import subprocess
from pathlib import Path

def run_one(kind: str, day: str, out_path: str) -> bool:
    env = os.environ.copy()
    env["NELAYA_KIND"] = kind
    env["NELAYA_DAY"] = day
    env["NELAYA_OUT"] = str(out_path)

    # opsional kalau script butuh COP/PY path
    root = Path(__file__).resolve().parents[1]
    env.setdefault("NELAYA_ROOT", str(root))
    env.setdefault("NELAYA_COP", str(root / ".venv" / "bin" / "copernicusmarine"))
    env.setdefault("NELAYA_PY", str(root / ".venv" / "bin" / "python"))

    r = subprocess.run(
        ["bash", "scripts/_cmems_download_one.sh"],
        env=env,
        text=True,
        capture_output=True,
    )
    if r.returncode == 0:
        return True
    # biar kelihatan errornya apa
    print(r.stdout)
    print(r.stderr)
    return False
