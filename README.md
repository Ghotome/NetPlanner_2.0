# Network Planner

Cross-platform network planning app with map and topology overlays (PySide6 + Qt WebEngine).

## Requirements
- Python 3.11+

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Run
```bash
python -m app
# or
netplanner
```

## Roadmap (high level)
- v0.1.0: empty shell builds
- v0.2.0: domain model + UI skeleton
- v0.3.0: map + nodes
- v0.4.0: links
- v0.5.0: elevation overlay
- v0.6.0: LOS/Fresnel analysis
- v0.7.0: coverage sectors
- v0.8.0: save/load project
- v0.9.0: monitoring
- v1.0.0: equipment access
