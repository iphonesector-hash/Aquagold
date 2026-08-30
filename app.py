import os

# Ensure production can start even when Vercel has no explicit session secret yet.
import aquagold_secret_bootstrap  # noqa: E402,F401
import app_v3
app = app_v3.app

# Stable core extensions first.
import app_extras  # noqa: E402,F401
import app_commerce  # noqa: E402,F401
import app_routing  # noqa: E402,F401
import aqua_ai  # noqa: E402,F401
import bale_bridge  # noqa: E402,F401
import bale_bootstrap  # noqa: E402,F401

# Schema is migration-owned. Runtime imports register routes only and never execute DDL.
import operational_v8  # noqa: E402,F401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
