import sys
from pathlib import Path

# Make the project root importable without installing.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
