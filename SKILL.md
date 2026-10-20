---
name: dawnwalker-save-tools
description: Decompress and timeline-diff The Blood of Dawnwalker DSAV saves (Oodle/Kraken chunks, NAME table, hashed quest facts, quest-graph nodes). Use when a player asks what a session completed or changed, or whether a quest started or closed.
---

# The Blood of Dawnwalker — save format & workflow

## Locating saves

`%LOCALAPPDATA%\Dawnwalker\Saved\SaveGames\*.sav` (+ `.meta` sidecars). Non-DSAV files there (e.g. settings saves) are skipped.

## Container

- `DSAV` magic, 36-byte header, then repeated chunks:
  `"CHNK" + u32 compressed_size + u32 uncompressed_size + payload`
- Payload begins with a 2-byte block header. If bit `0x40` of byte 0 is set, it's a **stored** block (raw bytes follow). Otherwise it's a **Oodle Kraken** stream. Decompress via ooz (see `docs/building-ooz.md`).
- Saves aren't encrypted.

## Decompressed layout

1. **State stream**: bit-packed, shifts between saves. Never byte-diff it.
2. **NAME table**: length-prefixed (u8) latin-1 strings ending at the `NAMEDWNT` marker
3. **Node tree** (tail of file): `u16 N` after `NAMEDWNT`, then N 16-byte records `<HhIII>` = `(id, parent, offset, size, name_index)`. `offset - 36` indexes the decompressed buffer. Records point at named subsystem blobs.

### Subsystem blobs

- **`QuestSystemImpl`**: fact table at blob offset 6: `u32 count`, then `count × (u32 hash, i32 value)`.
- **`QuestHelperImpl`**: `u16 L` at offset 4, skip `L` bytes, `u32 n` + `n×8` bytes, `u16 cnt`, then `cnt × (u64 root, u64 node, u64 value)`. Thousands of slots; the **nonzero** entries (~dozens) are live quest activity.

### Fact-name hashing

Case-insensitive CRC-32 variant (poly `0x04C11DB7`, MSB-first table, fed both bytes of each UTF-16 code unit of the uppercased name). Verified convention: `q.m.<major>.fact|int|float.<word>` (e.g. `q.m.103.fact.proceed`). **Most facts do not follow it.** Blind vocabulary brute-forcing cracks only a handful per hour. A full name→hash map would need game assets.

## The method that works: timeline diff

Hash reversal is mostly a dead end. Diffing parsed tables across saves answers the real question ("what did I finish?") without it.

1. Collect **4+ saves** spanning a session, and note what you did between them. That event mapping is what makes the deltas interpretable.
2. `dwsave.py timeline` diffs facts and graph nodes across all saves in chronological order.
3. Read transitions:
   - `None → 1` = started/opened
   - `1 → 0`, or a node vanishing = closed
   - Monotonic increases = counters (money, day count, world progress)
4. **Reopen trap:** a quest that reopens creates a new node while the old one deactivates. In a single snapshot that looks identical to "closed". Only a timeline separates them.
5. A quicksave just before a choice shows up byte-level as the pre-choice state, so it's the reload target for redoing that choice.

### Journal objects (NAME table)

`/Journal/(\w+)\.\w+` matches in the NAME table give the open journal inventory: `q1xx` main stages, `sq7xx` side quests, `ob1xx` court, `poi`/`npoi` open-world meta. New names between saves = newly started; vanished names = closed.

⚠ **Completed quests often leave NO journal object.** "No trace in the NAME table" does **not** mean "never started". Check the in-game journal's Completed tab before telling a player a quest is undone. Reliable save-derived signals are: new journal objects, vanished journal objects, and timestamped fact/graph deltas.

## Pitfalls

- Diff **parsed tables**, never raw state-stream bytes. Bit-packing shifts produce thousands of false positives.
- A naming guess that cracks one fact hash usually doesn't carry over to the next quest family. Check it against a second family before investing; if it fails, use the timeline answer.
- On Windows OpenSSH, `scp host:'dir/*.sav'` can't expand globs. Stream `ssh host 'cd dir && tar -cf - *.sav *.meta' | tar -xf -` instead (that's what `pull --host` does).
