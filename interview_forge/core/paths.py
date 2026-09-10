"""Canonical repository paths shared by runtime and build code.

Keeping these paths in one module changes no public URL or database location;
it only prevents a moved Python module from deriving paths from its new folder.
"""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "hot100-study.db"
AUTH_DB_PATH = DATA_DIR / "auth.db"
USERS_DIR = DATA_DIR / "users"
