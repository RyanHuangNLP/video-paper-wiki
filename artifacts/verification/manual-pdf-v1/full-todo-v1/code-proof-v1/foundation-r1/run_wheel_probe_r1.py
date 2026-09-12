"""Bind the unchanged installed probe to the successful second offline build."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

here = Path(__file__).parent
script = here / "foundation_wheel_probe_r1.py"
assert hashlib.sha256(script.read_bytes()).hexdigest() == "efbd369ba7e421b0dfebcdf5669ff6157eeda17555e6b3a0edc301d850d3d378"
build_path = here / "wheel-build-r2/foundation-wheel-build-r2.json"
build = json.loads(build_path.read_text())
assert build["exit_code"] == 0
assert build["wheel"]["sha256"] == "51ed433d7cccbe9c4d93c103c9d3b7cfa1bbc37f8af1440f017f98c617b62629"
spec = importlib.util.spec_from_file_location("foundation_probe_r1", script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.BUILD_RESULT_PATH = build_path
sys.argv = [str(script), "--wheel", build["wheel"]["path"]]
raise SystemExit(module.main())
