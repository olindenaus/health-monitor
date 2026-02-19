# Health Monitor

Personal health event tracker. Log food, symptoms, activities and mood from the CLI, correlate them with objective Garmin biometrics (sleep, stress, HRV, steps) to find triggers — initially for skin inflammation.

---

## How to use

### Setup

```bash
git clone <repo>
cd health_monitor
python3 -m venv .venv
.venv/bin/pip install -e .
```

### Logging events

```bash
# Food
.venv/bin/hm log food avocado --category regular
.venv/bin/hm log food alcohol --category junk
.venv/bin/hm log food "white bread" --category simple_carbs

# Symptoms (0–10 scale)
.venv/bin/hm symptom face_redness 6
.venv/bin/hm symptom face_redness 3 --notes "after good sleep"

# Activities
.venv/bin/hm log activity gaming --notes "2h"
.venv/bin/hm log activity workout --notes "45min run"

# Stress / mood
.venv/bin/hm log stress 7
.venv/bin/hm log mood relaxed
```

### Viewing data

```bash
# Today's summary
.venv/bin/hm today

# Recent events (all)
.venv/bin/hm list

# Filter by tag
.venv/bin/hm list --tag food
.venv/bin/hm list --tag symptom --today
```

### Syncing Garmin data

First-time full download (run once):
```bash
.venv/bin/garmindb_cli.py --all --download --import --analyze
```

Daily incremental update:
```bash
.venv/bin/garmindb_cli.py --all --download --import --analyze --latest
```

Sync Garmin daily summaries into health.db:
```bash
.venv/bin/python scripts/garmin_sync.py           # last 30 days
.venv/bin/python scripts/garmin_sync.py --days 90  # last 90 days
```

The sync populates the `garmin_daily` table with: steps, resting HR, avg HR, stress score, sleep duration, REM sleep, and active calories — one row per day. This table can be joined with the `events` table on `date(events.timestamp) = garmin_daily.day` for correlation analysis.

---

## Project structure

```
health_monitor/
├── health_monitor/
│   ├── db.py        # SQLite schema and queries
│   └── cli.py       # hm CLI (log, symptom, list, today)
├── scripts/
│   └── garmin_sync.py   # Pull Garmin data into health.db
├── data/
│   └── health.db    # SQLite database (gitignored)
└── notebooks/       # Jupyter notebooks for analysis (Phase 4)
```

---

## Roadmap

- [x] Phase 1 — CLI event logger
- [x] Phase 2 — Garmin data sync (sleep, steps, stress, HR)
- [ ] Phase 3 — Voice input (Whisper + LLM parsing)
- [ ] Phase 4 — Correlation analysis notebook
