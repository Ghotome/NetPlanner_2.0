#!/usr/bin/env python3
from pathlib import Path
import tomllib


root = Path(__file__).resolve().parents[1]
with (root / "pyproject.toml").open("rb") as fh:
    data = tomllib.load(fh)

print(data["project"]["version"])
