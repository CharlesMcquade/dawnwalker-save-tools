# Building ooz (Oodle/Kraken decompressor)

Dawnwalker save chunks are Oodle **Kraken** streams. Oodle has no dependable Python binding, so `dwsave.py` loads [powzix/ooz](https://github.com/powzix/ooz), an open-source reimplementation, as a shared library via `ctypes` and calls the C++-mangled symbol `_Z17Kraken_DecompressPKhmPhm` (`int Kraken_Decompress(const uint8_t*, size_t, uint8_t*, size_t)`).

ooz is an MSVC/x86 project. `python3 scripts/dwsave.py rebuild` does the following:

1. `git clone https://github.com/powzix/ooz scripts/ooz`
2. Writes stub headers into `scripts/ooz_stub/`:
   - `targetver.h`, `SDKDDKVer.h`, `tchar.h`: empty or near-empty
   - `Windows.h`: `WINAPI`, `HINSTANCE`, `LARGE_INTEGER`, and no-op `LoadLibraryA` / `GetProcAddress` / `QueryPerformance*`. These are only used by ooz's CLI and benchmark code, never by the decompress path.
   - `intrin.h`: includes **sse2neon.h** (SSE2 → NEON translation) on arm64 or `<x86intrin.h>` on x86_64, and provides `_BitScanForward/Reverse`, `_byteswap_*`, `_rotl`
   - `msvc_compat.h` (force-included): `#define __int64 long long` (must be `long long`, not `int64_t`, or ooz's `typedef unsigned __int64` breaks) and `__forceinline`
3. On arm64 only, downloads `sse2neon.h` from [DLTcollab/sse2neon](https://github.com/DLTcollab/sse2neon)
4. Compiles `kraken.cpp` (with `-Dmain=ooz_main`, because ooz ships a CLI `main` that would otherwise clash), `bitknit.cpp`, `lzna.cpp` with `g++ -O2 -fPIC` (plus `-msse4.1` on x86_64)
5. Links `scripts/libooz.dylib` (macOS) or `scripts/libooz.so` (Linux)

Pitfalls hit getting here:

- Including `<immintrin.h>` on arm64 fails ("only meant to be used on x86"). Route `intrin.h` to sse2neon instead.
- On x86_64, `<x86intrin.h>` already defines `_rotl` as a macro, so the stub's own `_rotl` is guarded with `#ifndef _rotl`.
- Don't try zlib/lz4 on these chunks. No readable strings in the body means compression, not encryption.

Tested: macOS arm64 (Apple clang), Linux arm64 (Debian g++), Linux x86_64 (Debian g++ in the `python:3.12` image). All decode identically. Windows: use WSL.
