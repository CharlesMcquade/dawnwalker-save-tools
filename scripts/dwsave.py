#!/usr/bin/env python3
"""
Dawnwalker save toolkit (The Blood of Dawnwalker, DSAV format).

Self-contained: decompresses .sav files (Oodle/Kraken), parses the NAME table,
QuestSystemImpl facts (hashed) and QuestHelperImpl quest-graph entries, and
diffs them across a timeline of saves. Facts are hashed by the game, so this
tool reports RAW HASHES + VALUES + timeline deltas — enough to answer
"what changed between saves" without any game asset tables.

Usage:
  python3 dwsave.py pull                  # copy saves -> ./saves/ (local, or --host over ssh)
  python3 dwsave.py list                  # list local saves by mtime
  python3 dwsave.py timeline              # chronological fact/graph diff of ALL local saves
  python3 dwsave.py dump <file.sav>       # full dump: facts (hash=val) + active graph nodes
  python3 dwsave.py diff A.sav B.sav      # two-save diff
  python3 dwsave.py rebuild               # rebuild libooz from bundled ooz source

Requires: libooz.dylib (macOS) / libooz.so (Linux) next to this file; build with `rebuild`.
Windows: run under WSL (rebuild needs g++).

Options / env vars:
  --saves DIR   (DWSAVE_DIR)   local save cache, default ./saves
  --host H      (DWSAVE_HOST)  pull over ssh from host H (else copy locally)
  --path P      (DWSAVE_PATH)  save dir; default %LOCALAPPDATA%/Dawnwalker/Saved/SaveGames
"""
import ctypes, glob, shutil, struct, sys, os, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
import platform
_SYS, _ARCH = platform.system(), platform.machine().lower()
LIB = os.path.join(HERE, "libooz.dylib" if _SYS == "Darwin" else "libooz.so")


def _opt(name, env, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        val = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return val
    return os.environ.get(env, default)

SAVES_DIR = _opt("--saves", "DWSAVE_DIR", "saves")
HOST = _opt("--host", "DWSAVE_HOST")
SAVE_PATH = _opt("--path", "DWSAVE_PATH",
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Dawnwalker", "Saved", "SaveGames"))

# --- Oodle/Kraken -------------------------------------------------------------
_kraken = None
def kraken():
    global _kraken
    if _kraken is None:
        if not os.path.exists(LIB):
            if _SYS == "Windows":
                sys.exit("decoding needs the ooz library, which builds on macOS/Linux only - run this under WSL ('pull' works natively)")
            sys.exit("%s missing - run: python3 dwsave.py rebuild" % os.path.basename(LIB))
        lib = ctypes.CDLL(LIB)
        fn = lib._Z17Kraken_DecompressPKhmPhm
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
        _kraken = fn
    return _kraken

def decompress_dsav(path):
    """DSAV container -> raw decompressed bytes."""
    d = open(path, "rb").read()
    if d[:4] != b"DSAV":
        raise ValueError("not a DSAV save: %s" % path)
    o = 36
    data = b""
    while o + 12 < len(d) and d[o:o+4] == b"CHNK":
        comp, unc = struct.unpack_from("<II", d, o+4)
        blk = d[o+12:o+12+comp]
        if blk[0] & 0x40:                       # stored block
            data += blk[2:2+unc]
        else:
            out = ctypes.create_string_buffer(unc + 64)
            n = kraken()(blk, comp, out, unc)
            if n <= 0:
                raise RuntimeError("kraken decompress failed in %s @%d" % (path, o))
            data += out.raw[:n]
        o += 12 + comp
    return data

# --- NAME table / node tree ---------------------------------------------------
def names_of(d):
    i = d.rfind(b"NAMEDWNT")
    j = d.rfind(b"NAME", 0, i)
    p = j + 8
    out = []
    while p < i:
        L = d[p]
        out.append(d[p+1:p+1+L].decode("latin1"))
        p += 1 + L
    return out

def tree2(d):
    nm = names_of(d)
    N = struct.unpack_from("<H", d, d.rfind(b"NAMEDWNT") + 8)[0]
    start = len(d) - 16 - 16 * N
    return nm, [struct.unpack_from("<HhIII", d, start + 16*k) for k in range(N)]

def blob_by_name(d, nodename):
    nm, recs = tree2(d)
    for i, r in enumerate(recs):
        if i and nm[r[4]] == nodename:
            off, size = r[2] - 36, r[3]
            return d[off:off+size]
    return None

# --- QuestSystemImpl facts ----------------------------------------------------
def facts_of(d):
    """{hash: value} from QuestSystemImpl."""
    b = blob_by_name(d, "QuestSystemImpl")
    if b is None:
        return {}
    n = struct.unpack_from("<I", b, 6)[0]
    return {struct.unpack_from("<I", b, 10+8*k)[0]: struct.unpack_from("<i", b, 10+8*k+4)[0]
            for k in range(n)}

# --- QuestHelperImpl quest graph ----------------------------------------------
def helper_entries(b):
    """[(root:u64, node:u64, value:u64)] from QuestHelperImpl."""
    L = struct.unpack_from("<H", b, 4)[0]
    o = 6 + L
    n = struct.unpack_from("<I", b, o)[0]
    o += 4 + 8 * n
    cnt = struct.unpack_from("<H", b, o)[0]
    eo = o + 2
    return [struct.unpack_from("<QQQ", b, eo + 24*i) for i in range(cnt)]

def graph_of(d):
    b = blob_by_name(d, "QuestHelperImpl")
    if b is None:
        return {}
    return {(e[0], e[1]): e[2] for e in helper_entries(b) if e[2] != 0}

# --- known fact-name hashes (CRC-32/MPEG-2-style over UTF-16 of uppercased name)
_T = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xffffffff if _c & 0x80000000 else (_c << 1) & 0xffffffff
    _T.append(_c)

def fact_hash(s):
    h = 0
    for ch in s.upper():
        o = ord(ch)
        h = ((h >> 8) & 0xFFFFFF) ^ _T[(h ^ o) & 0xFF]
        h = ((h >> 8) & 0xFFFFFF) ^ _T[(h ^ (o >> 8)) & 0xFF]
    return h & 0xFFFFFFFF

KNOWN_FACTS = {}
for maj in (101, 102, 103, 104, 105, 199):
    for w in ("proceed", "alley_found", "thief02", "drainingdungeonshook"):
        KNOWN_FACTS[fact_hash("q.m.%d.fact.%s" % (maj, w))] = "q.m.%d.fact.%s" % (maj, w)
        KNOWN_FACTS[fact_hash("q.m.%d.int.%s" % (maj, w))] = "q.m.%d.int.%s" % (maj, w)
        KNOWN_FACTS[fact_hash("q.m.%d.float.%s" % (maj, w))] = "q.m.%d.float.%s" % (maj, w)

def hname(h):
    return KNOWN_FACTS.get(h, "0x%08x" % h)

# --- commands ------------------------------------------------------------------
def cmd_pull(args):
    os.makedirs(SAVES_DIR, exist_ok=True)
    if not HOST:
        for src in glob.glob(os.path.join(SAVE_PATH, "*.sav")) + glob.glob(os.path.join(SAVE_PATH, "*.meta")):
            shutil.copy2(src, SAVES_DIR)
        return cmd_list(args)
    # Windows OpenSSH scp can't expand remote globs; stream a tar over ssh instead.
    # SAVE_PATH must be in the remote shell's syntax (e.g. git-bash: /c/Users/<you>/AppData/Local/...)
    cmd = ["ssh", HOST, 'cd "%s" && tar -cf - *.sav *.meta' % SAVE_PATH]
    print(" ".join(cmd))
    with open(os.path.join(SAVES_DIR, "_bundle.tar"), "wb") as fh:
        subprocess.run(cmd, stdout=fh, check=True)
    subprocess.run(["tar", "-xf", os.path.join(SAVES_DIR, "_bundle.tar"), "-C", SAVES_DIR], check=True)
    os.remove(os.path.join(SAVES_DIR, "_bundle.tar"))
    cmd_list(args)

def cmd_list(args):
    files = sorted(f for f in os.listdir(SAVES_DIR) if f.endswith(".sav")) if os.path.isdir(SAVES_DIR) else []
    for f in files:
        p = os.path.join(SAVES_DIR, f)
        print("%s  %s" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))), f))

def _loads(paths):
    out = {}
    for p in paths:
        try:
            d = decompress_dsav(p)
            out[os.path.basename(p)] = (facts_of(d), graph_of(d))
        except Exception as e:
            print("SKIP %s: %s" % (p, e), file=sys.stderr)
    return out

def _fmt_delta(seq):
    return " -> ".join("None" if v is None else str(v) for v in seq)

def cmd_timeline(args):
    paths = [os.path.join(SAVES_DIR, f) for f in sorted(
        (f for f in os.listdir(SAVES_DIR) if f.endswith(".sav")),
        key=lambda f: os.path.getmtime(os.path.join(SAVES_DIR, f)))]
    loads = _loads(paths)
    names = list(loads)
    print("Timeline (%d saves, oldest first):" % len(names))
    for n in names:
        print("  %-22s facts=%-5d graph_active=%d" % (n, len(loads[n][0]), len(loads[n][1])))

    allf = set().union(*[set(v[0]) for v in loads.values()])
    fac_events = []
    for h in sorted(allf):
        seq = [loads[n][0].get(h) for n in names]
        if any(x != seq[0] for x in seq):
            fac_events.append((h, seq))
    print("\nFACT deltas (%d):" % len(fac_events))
    for h, seq in fac_events:
        print("  %-32s %s" % (hname(h), _fmt_delta(seq)))

    allg = set().union(*[set(v[1]) for v in loads.values()])
    graph_events = []
    for k in sorted(allg):
        seq = [loads[n][1].get(k) for n in names]
        if any(x != seq[0] for x in seq):
            graph_events.append((k, seq))
    print("\nQUEST-GRAPH deltas (%d):" % len(graph_events))
    for (root, node), seq in graph_events:
        print("  root=%016x node=%-6d %s" % (root, node, _fmt_delta(seq)))

def cmd_dump(args):
    d = decompress_dsav(args[0])
    f = facts_of(d)
    print("FACTS (%d):" % len(f))
    for h in sorted(f):
        print("  %-32s = %d" % (hname(h), f[h]))
    g = graph_of(d)
    print("\nACTIVE QUEST-GRAPH NODES (%d):" % len(g))
    for (root, node) in sorted(g):
        print("  root=%016x node=%-6d val=%d" % (root, node, g[(root, node)]))

def cmd_diff(args):
    loads = _loads(args[:2])
    (n1, (f1, g1)), (n2, (f2, g2)) = list(loads.items())
    print("%s -> %s" % (n1, n2))
    for h in sorted(set(f1) | set(f2)):
        v1, v2 = f1.get(h), f2.get(h)
        if v1 != v2:
            print("  FACT %-32s %s -> %s" % (hname(h), v1, v2))
    for k in sorted(set(g1) | set(g2)):
        v1, v2 = g1.get(k), g2.get(k)
        if v1 != v2:
            print("  GRAPH root=%016x node=%-6d %s -> %s" % (k[0], k[1], v1, v2))

_STUBS = {
    "targetver.h": "#pragma once\n",
    "SDKDDKVer.h": "#pragma once\n",
    "tchar.h": "#pragma once\n#define _tmain main\n",
    "msvc_compat.h": (
        "#pragma once\n#include <stdint.h>\n#include <sys/stat.h>\n"
        "#define __int64 long long\n"
        "#define __forceinline inline __attribute__((always_inline))\n"),
    "Windows.h": (
        "#pragma once\n#include <stdint.h>\n#include <stddef.h>\n#define WINAPI\n"
        "typedef void *HINSTANCE;\n"
        "typedef union { struct { uint32_t LowPart; int32_t HighPart; }; int64_t QuadPart; } LARGE_INTEGER;\n"
        "static inline HINSTANCE LoadLibraryA(const char *n){ (void)n; return 0; }\n"
        "static inline void *GetProcAddress(HINSTANCE m, const char *n){ (void)m; (void)n; return 0; }\n"
        "static inline int QueryPerformanceCounter(void *p){ *(long long*)p = 0; return 1; }\n"
        "static inline int QueryPerformanceFrequency(void *p){ *(long long*)p = 1; return 1; }\n"),
    "intrin.h": (
        "#pragma once\n#include <stdint.h>\n"
        "#if defined(__aarch64__) || defined(__arm64__)\n#include \"sse2neon.h\"\n#else\n#include <x86intrin.h>\n#endif\n"
        "static inline unsigned char _BitScanForward(unsigned long *i, uint32_t m){ if(!m) return 0; *i=__builtin_ctz(m); return 1; }\n"
        "static inline unsigned char _BitScanReverse(unsigned long *i, uint32_t m){ if(!m) return 0; *i=31-__builtin_clz(m); return 1; }\n"
        "static inline uint16_t _byteswap_ushort(uint16_t x){ return __builtin_bswap16(x); }\n"
        "static inline uint32_t _byteswap_ulong(uint32_t x){ return __builtin_bswap32(x); }\n"
        "static inline uint64_t _byteswap_uint64(uint64_t x){ return __builtin_bswap64(x); }\n"
        "#ifndef _rotl\n"   # x86intrin.h already provides _rotl as a macro
        "static inline uint32_t _rotl(uint32_t x, int c){ c &= 31; return c ? (x<<c)|(x>>(32-c)) : x; }\n"
        "#endif\n"),
}

def cmd_rebuild(args):
    """Build libooz (macOS dylib / Linux .so, arm64 or x86_64) from powzix/ooz with stub MSVC headers."""
    if _SYS not in ("Darwin", "Linux"):
        sys.exit("rebuild supports macOS and Linux only (on Windows use WSL)")
    arm = _ARCH in ("arm64", "aarch64")
    src = os.path.join(HERE, "ooz")
    if not os.path.isdir(src):
        subprocess.run(["git", "clone", "https://github.com/powzix/ooz", src], check=True)
    stub = os.path.join(HERE, "ooz_stub")
    os.makedirs(stub, exist_ok=True)
    for name, body in _STUBS.items():
        open(os.path.join(stub, name), "w").write(body)
    if arm and not os.path.exists(os.path.join(stub, "sse2neon.h")):
        subprocess.run(["curl", "-fsSL", "-o", os.path.join(stub, "sse2neon.h"),
                        "https://raw.githubusercontent.com/DLTcollab/sse2neon/master/sse2neon.h"], check=True)
    cxx = os.environ.get("CXX", "g++")
    flags = ["-O2", "-w", "-fPIC"] + (["-msse4.1"] if not arm else [])
    objs = []
    for srcf in ("kraken.cpp", "bitknit.cpp", "lzna.cpp"):
        obj = os.path.join(HERE, srcf.replace(".cpp", ".o"))
        extra = ["-Dmain=ooz_main"] if srcf == "kraken.cpp" else []   # ooz ships a CLI main()
        subprocess.run([cxx] + flags + ["-I", stub, "-include", os.path.join(stub, "msvc_compat.h"),
                        "-D_CONSOLE", "-c", os.path.join(src, srcf), "-o", obj] + extra, check=True)
        objs.append(obj)
    subprocess.run([cxx, "-shared", "-o", LIB] + objs, check=True)
    for o in objs:
        os.remove(o)
    print("built", LIB)

COMMANDS = {"pull": cmd_pull, "list": cmd_list, "timeline": cmd_timeline,
            "dump": cmd_dump, "diff": cmd_diff, "rebuild": cmd_rebuild}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
