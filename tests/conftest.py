"""Pytest configuration and fixtures for sushbotseller tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path so imports work in CI
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# Common test fixtures can be added here
