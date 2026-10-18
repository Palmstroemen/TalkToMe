import os
import sys

# Make ttm_core (repo root) and talktome_service (service/) importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "service"))
