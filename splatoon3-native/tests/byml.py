"""Compatibility import for the shared local BYML reader."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.byml import read
