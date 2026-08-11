import os
import sys

# Insert the repo root so `backend.*` imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
# Also insert backend/ so bare imports (e.g. `from config import Config`) work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
