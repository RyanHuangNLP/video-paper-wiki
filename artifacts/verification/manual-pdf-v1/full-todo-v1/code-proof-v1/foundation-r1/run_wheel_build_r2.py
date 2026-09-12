"""Retry the unchanged offline build with separate evidence after cache refusal."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

here = Path(__file__).parent
script = here / "build_foundation_wheel_r1.py"
assert hashlib.sha256(script.read_bytes()).hexdigest() == "33c4071074b38f383915e9b62a42b562472b1d88bf47081d8bbeaf2756ce4a11"
prior = json.loads((here / "foundation-wheel-build-r1.json").read_text())
assert prior["exit_code"] == 2 and prior["wheel"] is None
evidence = here / "wheel-build-r2"
evidence.mkdir()
spec = importlib.util.spec_from_file_location("foundation_build_r2", script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.ARTIFACT_ROOT = evidence
module.RESULT_PATH = evidence / "foundation-wheel-build-r2.json"
raise SystemExit(module.main())
