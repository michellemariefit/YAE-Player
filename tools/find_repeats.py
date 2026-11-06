"""
Find repeated passages in a lesson transcript.

    python tools/find_repeats.py "The Parent Playbook"

Reads tools/lessons/transcripts/<name>.json and prints every stretch of speech that says
the same thing (8+ matching words in a row, allowing small wording changes) as an
earlier stretch, with timestamps. Those are the candidates for cutting. Also writes
tools/lessons/cuts/<name>.json as a starting cut list that cut_video.py can render:
    {"keep": [[0, 12.4], [15.0, 60.2], ...]}      seconds to keep, in order
"""
import json, os, re, sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(ROOT, "tools", "lessons", "transcripts")
CUTS = os.path.join(ROOT, "tools", "lessons", "cuts")
MIN_WORDS = 8          # a match shorter than this is just a common phrase
STOP = set("the a an and or to of in on for is it that this you your i we so um uh like just".split())


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def main(name):
    data = json.load(open(os.path.join(TR, name + ".json")))
    words = [(norm(w["w"]), w["s"], w["e"]) for s in data["segments"] for w in s["words"] if norm(w["w"])]
    toks = [w for (w, _, _) in words]
    sm = SequenceMatcher(None, toks, toks, autojunk=False)
    # compare the transcript with itself, ignoring the trivial diagonal: look for matching blocks off-diagonal
    found = []
    n = len(toks)
    # sliding: for each start i, find a later j with a long matching run
    index = {}
    K = 5
    for i in range(n - K):
        index.setdefault(tuple(toks[i:i + K]), []).append(i)
    seen = set()
    for key, starts in index.items():
        if len(starts) < 2 or all(t in STOP for t in key):
            continue
        for a in starts:
            for b in starts:
                if b <= a + K or (a, b) in seen:
                    continue
                # extend the match forward
                L = K
                while a + L < b and b + L < n and toks[a + L] == toks[b + L]:
                    L += 1
                if L >= MIN_WORDS:
                    for d in range(L):
                        seen.add((a + d, b + d))
                    found.append((b, b + L, a, a + L))
    # merge overlapping later-occurrences
    found.sort()
    merged = []
    for b0, b1, a0, a1 in found:
        if merged and b0 <= merged[-1][1] + 3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b1), merged[-1][2], max(merged[-1][3], a1))
        else:
            merged.append((b0, b1, a0, a1))
    dur = data["duration"]
    total_cut = 0
    print(f"{name}: {dur/60:.1f} min, {len(merged)} repeated passages\n")
    cut_ranges = []
    for b0, b1, a0, a1 in merged:
        t0, t1 = words[b0][1], words[min(b1, n - 1)][2]
        f0, f1 = words[a0][1], words[min(a1, n - 1)][2]
        text = " ".join(w["w"].strip() for s in data["segments"] for w in s["words"] if t0 <= w["s"] <= t1)
        print(f"[{int(t0)//60:02d}:{int(t0)%60:02d} to {int(t1)//60:02d}:{int(t1)%60:02d}]  ({t1-t0:.0f}s)  repeats [{int(f0)//60:02d}:{int(f0)%60:02d}]")
        print("   " + text[:220] + ("..." if len(text) > 220 else "") + "\n")
        total_cut += t1 - t0
        cut_ranges.append([round(t0, 2), round(t1, 2)])
    print(f"Repeated speech: {total_cut/60:.1f} min of {dur/60:.1f}. Cutting it all leaves {(dur-total_cut)/60:.1f} min.")
    # keep list = everything except the cut ranges
    keep, pos = [], 0.0
    for c0, c1 in cut_ranges:
        if c0 > pos:
            keep.append([round(pos, 2), c0])
        pos = max(pos, c1)
    if pos < dur:
        keep.append([round(pos, 2), round(dur, 2)])
    os.makedirs(CUTS, exist_ok=True)
    out = os.path.join(CUTS, name + ".json")
    if not os.path.exists(out):
        json.dump({"source": data["file"], "keep": keep, "note": "seconds to keep, in order. Edit by hand, then run tools/cut_video.py"}, open(out, "w"), indent=1)
        print("wrote", os.path.relpath(out, ROOT))
    else:
        print("cut list already exists, not overwritten:", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    for n in sys.argv[1:] or [f[:-5] for f in sorted(os.listdir(TR)) if f.endswith(".json")]:
        main(n)
        print("=" * 70)
