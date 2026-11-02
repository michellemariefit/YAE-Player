"""
Work out which Dropbox recording each YouTube demo came from.

    python tools/match_sources.py

The photo in each workout PDF is a frame from the original recording. This script compares
every PDF photo (images/<video id>-pdf.webp) with frames from every recording in
tools/cache/ and writes tools/sources.json: YouTube ID -> {file, matchSeconds, score}.
grab_frames.py reads that file to know which recording to open. Check the low scores by
hand; anything under 0.6 is a guess.
"""
import glob, json, os, sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "cache")
IMAGES = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "tools", "sources.json")
SIZE = (64, 36)
FPS = 3


def sig(frame):
    g = cv2.cvtColor(cv2.resize(frame, SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    g -= g.mean()
    n = np.linalg.norm(g)
    return g / n if n else g


def video_sigs(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps / FPS)))
    sigs, times, i = [], [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            sigs.append(sig(fr)); times.append(i / fps)
        i += 1
    cap.release()
    return np.array(sigs), times


def main():
    files = sorted(f for f in glob.glob(os.path.join(CACHE, "*")) if f.lower().endswith((".mov", ".mp4")))
    print(f"indexing {len(files)} recordings")
    index = {}
    for f in files:
        s, t = video_sigs(f)
        index[os.path.basename(f)] = (s, t)
        print("  ", os.path.basename(f), len(t), "frames")
    photos = sorted(glob.glob(os.path.join(IMAGES, "*-pdf.webp")))
    old = json.load(open(OUT)) if os.path.exists(OUT) else {}
    out = {k: v for k, v in old.items() if k.startswith("_")}
    out["_note"] = ("YouTube demo ID -> original recording in Dropbox (PRODUCTS & PROGRAMS / The Youth Athlete Edge / "
                    "Videos / Workouts). matchSeconds is where the PDF photo was taken from. Built by match_sources.py.")
    for p in photos:
        vid = os.path.basename(p)[:-9]
        ps = sig(cv2.imread(p))
        best = (-1, None, 0)
        for name, (sigs, times) in index.items():
            scores = sigs.reshape(len(sigs), -1) @ ps.reshape(-1)
            j = int(scores.argmax())
            if scores[j] > best[0]:
                best = (float(scores[j]), name, times[j])
        keep = old.get(vid, {})
        if keep.get("file") and keep.get("locked"):
            out[vid] = keep
        else:
            out[vid] = {"file": best[1], "matchSeconds": round(best[2], 1), "score": round(best[0], 3)}
        print(f"{vid}  {best[0]:.3f}  {best[1]}  @{best[2]:.1f}s")
    json.dump(out, open(OUT, "w"), indent=1)
    print("->", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    sys.exit(main())
