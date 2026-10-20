# dawnwalker-save-tools

Decompress and diff *The Blood of Dawnwalker* `.sav` files (DSAV container, Oodle/Kraken compression) to see **what actually changed between saves**: quest facts set, quest-graph nodes opened or closed, counters advancing.

> **Disclaimer:** Unofficial fan tooling based on reverse-engineering; not affiliated with Larian / Awaken Realms / Questline. May break on game updates. No game assets redistributed.

## What you can learn from saves

- Raw quest **facts** (`hash = value`) from the quest system, plus the live **quest-graph** nodes
- A chronological **timeline diff** across all your saves, which is the reliable way to answer "what did that session finish?"
- Open journal objects via the NAME table (newly started vs closed between saves)

Fact names are hashed by the game. The tool prints raw hashes except for a few cracked names. Timeline deltas answer most questions without names. See `SKILL.md`.

## Quickstart (macOS or Linux, arm64 or x86_64)

Needs Python 3, a C++ compiler (macOS: `xcode-select --install`; Linux: `g++`), git, curl. On Windows, run it under WSL. Native Windows Python can `pull` but can't decode.

```bash
git clone https://github.com/CharlesMcquade/dawnwalker-save-tools
cd dawnwalker-save-tools
python3 scripts/dwsave.py rebuild              # clones powzix/ooz, builds scripts/libooz.dylib (.so on Linux)
python3 scripts/dwsave.py dump /path/to/Autosave0.sav
python3 scripts/dwsave.py diff A.sav B.sav
python3 scripts/dwsave.py --saves /path/to/SaveGames timeline
```

Saves live at `%LOCALAPPDATA%\Dawnwalker\Saved\SaveGames\` on Windows. To pull them from a gaming PC over SSH into `./saves/`:

```bash
python3 scripts/dwsave.py --host mygamingpc --path "/c/Users/<you>/AppData/Local/Dawnwalker/Saved/SaveGames" pull
python3 scripts/dwsave.py timeline
```

Tested builds: macOS arm64, Linux arm64, Linux x86_64. See `docs/building-ooz.md`.

## Files

- `SKILL.md`: DSAV format and diff workflow (also usable as an AI-agent skill)
- `scripts/dwsave.py`: decompressor, parser, differ, ooz builder
- `docs/building-ooz.md`: what the ooz build does and why

License: MIT (this repo). ooz is fetched from its upstream at build time and keeps its own license.
