"""
AI WealthPilot API — FastAPI thin shell over the src/ quant core.

This package contains ONLY transport concerns: routing, validation,
caching, and serialization. All business logic stays in src/.
"""

import sys
from pathlib import Path

# Ensure the project root is importable regardless of the launch directory,
# so `from src.xxx import ...` works for any `api.*` import.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
