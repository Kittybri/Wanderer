"""Check reviewed manifest shrinkage against a Git base; no working-tree changes."""
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preservation_contract import removal_errors

def main():
    base = sys.argv[1]
    changes = json.loads(Path("preservation/intentional_changes.json").read_text())
    errors = []
    for name in ("commands", "features"):
        path = f"preservation/{name}.json"
        old = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True)
        if old.returncode:
            # First introduction only; do not silently ignore a deleted manifest later.
            check = subprocess.run(["git", "cat-file", "-e", base], capture_output=True)
            if check.returncode:
                raise SystemExit("Invalid preservation comparison base")
            continue
        if not Path(path).exists():
            errors.append(f"deleted manifest: {path}")
        else:
            errors.extend(removal_errors(json.loads(old.stdout), json.loads(Path(path).read_text()), changes))
    print(json.dumps({"unauthorized_removals": errors}))
    return bool(errors)
if __name__ == "__main__":
    raise SystemExit(main())
