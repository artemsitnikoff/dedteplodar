import os
import tempfile

# Must be set before any `admin.*` / `src.core.config` import (settings read env at import).
os.environ.setdefault("ADMIN_PASS", "test")
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
