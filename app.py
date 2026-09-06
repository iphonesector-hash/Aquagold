from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

# Reuse AquaGold's existing stable secret derivation. This keeps encrypted
# Bale settings readable without requiring a separate AQUAGOLD_SECRET_KEY
# when the production project already derives it from its database settings.
import aquagold_secret_bootstrap  # noqa: F401,E402

MODULE_PATH = Path(__file__).resolve().parent / "aqua-bale-standalone" / "app.py"
SPEC = spec_from_file_location("aqua_bale_standalone_app", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load standalone Aqua Bale application")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
app = MODULE.app
