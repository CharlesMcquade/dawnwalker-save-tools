# Dawnwalker Save Timeline

**dawnwalker-save-tools**: decode *The Blood of Dawnwalker* `.sav` files and see what changed between saves: quest facts set, quest-graph nodes opened or closed, journal entries started or finished. The headline feature is `timeline`, a chronological diff across every save in a folder that answers "what did that session actually finish?"

> Unofficial fan project. Not affiliated with or endorsed by Rebel Wolves or Bandai Namco Entertainment. The save format was reverse-engineered on PC saves and may change with future patches. Contains no game code or assets. The Oodle Kraken decoder is [powzix/ooz](https://github.com/powzix/ooz), an open-source reimplementation fetched from upstream at build time.

## Why this exists

In *The Blood of Dawnwalker*, quests run on a clock and choices close doors quietly. A session can resolve something without the journal making it obvious. Did that conversation finish the quest, or only move it along? The save records every quest flag the game set, but the format is compressed and the flag names are hashed. This tool decodes it and lines your saves up in order.

- **Where am I?** The quest flags, active quest-graph nodes and open journal entries from any save.
- **What did that session do?** `timeline` shows what each save started, closed or advanced compared with the one before it.
- **Which save do I reload?** A quicksave from just before a choice shows up as the pre-choice state, so you can find the right one.
- **What's next?** Give the timeline and `SKILL.md` to an AI agent. The tool reports state changes; the agent links them to the quest you were playing and suggests the next step, at whatever spoiler level you set. The tool itself contains no walkthrough.

## What it reads

Saves are a `DSAV` container of Oodle Kraken-compressed chunks. Once decoded, the tool parses:

- **Quest facts:** `hash = value` pairs from the quest system
- **Quest-graph nodes:** the live slots behind active quests
- **Journal objects** from the name table: main stages (`q1xx`), side quests (`sq7xx`), court (`ob1xx`), open-world points of interest

Fact names are hashed by the game. A few are cracked; the rest print as raw hashes. The timeline view doesn't need names, because the transitions (`None → 1` started, `1 → 0` closed, rising counters) carry the meaning.

## Quickstart

Needs Python 3, git, curl and a C++ compiler (macOS: `xcode-select --install`; Linux: `g++`).

```bash
git clone https://github.com/CharlesMcquade/dawnwalker-save-tools
cd dawnwalker-save-tools
python3 scripts/dwsave.py rebuild                      # one-time: builds the Kraken decoder
python3 scripts/dwsave.py --saves /path/to/SaveGames timeline
python3 scripts/dwsave.py diff Autosave0.sav Autosave1.sav
python3 scripts/dwsave.py dump Autosave0.sav
```

The `rebuild` step is tested on macOS arm64, Linux arm64 and Linux x86_64. On Windows, run it under WSL. Native Windows Python can `pull` saves but can't decode them.

## Where the saves are

```
%LOCALAPPDATA%\Dawnwalker\Saved\SaveGames\*.sav   (+ .meta sidecars)
```

To copy them into `./saves/` from the gaming PC over SSH:

```bash
python3 scripts/dwsave.py --host mygamingpc \
  --path "/c/Users/<you>/AppData/Local/Dawnwalker/Saved/SaveGames" pull
python3 scripts/dwsave.py timeline
```

For a useful timeline, keep four or more saves from one session and note what you did between them.

## Files

| Path | Purpose |
|---|---|
| `scripts/dwsave.py` | Decoder and parser: `dump`, `diff`, `timeline`, `list`, `pull`, `rebuild` |
| `docs/building-ooz.md` | How `rebuild` turns the MSVC/x86 ooz source into a macOS or Linux shared library |
| `SKILL.md` | DSAV layout, fact hashing and timeline-reading rules. Also usable as an AI-agent skill. |

## License

MIT for this repo. ooz keeps its own license.
