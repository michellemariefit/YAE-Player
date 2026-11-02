"""
Grab start and end position photos from each exercise's original recording.

Run from the yae-player folder:
    pip install opencv-python-headless numpy
    python tools/grab_frames.py

Where the videos come from:
  tools/sources.json maps each YouTube demo ID to the original recording in Dropbox
  (PRODUCTS & PROGRAMS / The Youth Athlete Edge / Videos / Workouts). Put those files in
  tools/cache/ with the same name. tools/match_sources.py builds sources.json by matching
  the PDF photos against the recordings. A source can set "searchFrom": seconds when the
  first rep is not near the start of the file.

What it does, for every exercise video in data/yae.json:
  1. Opens the recording in tools/cache/.
  2. Uses the photo Michelle chose for the PDF as the anchor (sources.json says where in the
     recording it is), then looks 3 seconds either side for the frame that looks most
     different from it. Frames are lined up first so a hand-held pan does not count as movement.
  3. The earlier of the two becomes the START photo and the later the END photo.
  4. Writes images/<video id>-start.webp and -end.webp, and adds
     startPhoto / endPhoto to each exercise in data/yae.json.
  5. Builds tools/review.html so you can check every pair at a glance.

If a pair is wrong (for example it caught her getting set up), add the exact seconds to
tools/overrides.json and run the script again:
    { "EXrX1lNTTio": { "start": 12.5, "end": 14.0 } }

Videos whose two photos already exist in images/ are kept as they are. To redo a pair on
purpose, pass its video ID (or --force alone to redo everything):
    python tools/grab_frames.py --force EXrX1lNTTio
The seconds used for each pair are remembered in tools/frames.json.
"""
import json, os, sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "cache")
IMAGES = os.path.join(ROOT, "images")
DATA = os.path.join(ROOT, "data", "yae.json")
OVERRIDES = os.path.join(ROOT, "tools", "overrides.json")
SOURCES = os.path.join(ROOT, "tools", "sources.json")
FRAMES = os.path.join(ROOT, "tools", "frames.json")   # seconds used for each pair, for review.html
SAMPLE_FPS = 6          # frames per second to analyse
SKIP_SECONDS = 2.0      # skip the very start of each video

os.makedirs(CACHE, exist_ok=True)
os.makedirs(IMAGES, exist_ok=True)
overrides = {k: v for k, v in (json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}).items()
             if not k.startswith("_")}
sources = {k: v for k, v in (json.load(open(SOURCES)) if os.path.exists(SOURCES) else {}).items()
           if not k.startswith("_")}


def exercises():
    data = json.load(open(DATA))
    for g in data["groups"]:
        for w in g["workouts"]:
            for b in w["blocks"]:
                for e in b["exercises"]:
                    yield w, e


def video_ids():
    ids = {}
    for w, e in exercises():
        if e.get("video"):
            ids.setdefault(e["video"], f"{e['name']} ({w['name']} {e['code']})")
        for a in e.get("alts", []):
            ids.setdefault(a["video"], f"{a['label']} (progression in {w['name']})")
    return ids


def source_path(vid):
    src = sources.get(vid)
    if not src or not src.get("file"):
        raise FileNotFoundError("no recording listed in tools/sources.json")
    out = os.path.join(CACHE, src["file"])
    if not os.path.exists(out):
        raise FileNotFoundError(f'put "{src["file"]}" from Dropbox in tools/cache/')
    return out


def small_gray(frame):
    g = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)


def masks(shape):
    border = np.ones(shape, dtype=bool); border[9:-9, 16:-16] = False
    return border, ~border


def aligned(a, b):
    """Shift b so it lines up with a (hand-held camera), using phase correlation."""
    (dx, dy), _ = cv2.phaseCorrelate(a, b)
    if abs(dx) > 40 or abs(dy) > 25:
        return b
    m = np.float32([[1, 0, -dx], [0, 1, -dy]])
    return cv2.warpAffine(b, m, (b.shape[1], b.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def window_frames(path, centre_t, span=3.0):
    """Full frames at SAMPLE_FPS from centre_t - span to centre_t + span."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps / SAMPLE_FPS)))
    t0 = max(0.0, centre_t - span)
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    frames, times, i = [], [], int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    while True:
        ok, frame = cap.read()
        if not ok or i / fps > centre_t + span:
            break
        if i % step == 0:
            frames.append(frame); times.append(i / fps)
        i += 1
    cap.release()
    return frames, times


def pick_pair(frames, times, anchor_t):
    """Index of the anchor frame and of the frame most different from it (body only, after
    lining the frames up). Returned in time order: (start, end)."""
    g = [small_gray(f) for f in frames]
    a = min(range(len(g)), key=lambda i: abs(times[i] - anchor_t))
    _, centre = masks(g[a].shape)
    def diff(i):
        return np.abs(g[a] - aligned(g[a], g[i]))[centre].mean()
    ok = lambda i: abs(times[i] - times[a]) >= 0.4 and g[i].mean() > 20   # skip black frames at the end of a file
    b = max(range(len(g)), key=lambda i: diff(i) if ok(i) else -1)
    return (a, b) if times[a] <= times[b] else (b, a)


def find_anchor(path, vid):
    """Where in the recording the PDF photo was taken from (used when sources.json lacks it)."""
    photo = os.path.join(IMAGES, f"{vid}-pdf.webp")
    if not os.path.exists(photo):
        return None
    ps = small_gray(cv2.imread(photo)); ps -= ps.mean(); ps /= (np.linalg.norm(ps) or 1)
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps / 3)))
    best, i = (-1, 0), 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            g = small_gray(fr); g -= g.mean(); g /= (np.linalg.norm(g) or 1)
            score = float((g * ps).sum())
            if score > best[0]:
                best = (score, i / fps)
        i += 1
    cap.release()
    return best[1]


def frame_at(path, seconds):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def save(frame, name):
    # trim black bars on the sides (one recording is pillarboxed)
    col = frame.mean(axis=(0, 2))
    lit = np.where(col > 12)[0]
    if len(lit) and (lit[0] > 8 or lit[-1] < frame.shape[1] - 9):
        frame = frame[:, lit[0]:lit[-1] + 1]
    h, w = frame.shape[:2]
    scale = 960 / max(h, w)
    if scale < 1:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(IMAGES, name), frame, [cv2.IMWRITE_WEBP_QUALITY, 82])
    return "images/" + name


def existing(vid):
    names = [f"{vid}-start.webp", f"{vid}-end.webp"]
    if all(os.path.exists(os.path.join(IMAGES, n)) for n in names):
        return ["images/" + n for n in names]
    return None


def main():
    args = sys.argv[1:]
    force_all = args == ["--force"]
    force = set(args[1:]) if args[:1] == ["--force"] else set()
    ids = video_ids()
    remembered = json.load(open(FRAMES)) if os.path.exists(FRAMES) else {}
    results, missing, sources_changed = {}, [], set()
    for n, (vid, name) in enumerate(ids.items(), 1):
        print(f"[{n}/{len(ids)}] {name} ({vid})")
        kept = existing(vid)
        if kept and not force_all and vid not in force and vid not in overrides:
            results[vid] = {"name": name, "start": kept[0], "end": kept[1],
                            "t": remembered.get(vid, {}).get("t", ["kept", "kept"]),
                            "file": remembered.get(vid, {}).get("file", "")}
            print("   kept existing photos")
            continue
        try:
            path = source_path(vid)
            if vid in overrides:
                s, e = overrides[vid]["start"], overrides[vid]["end"]
                fs, fe = frame_at(path, s), frame_at(path, e)
            else:
                src = sources.get(vid, {})
                anchor = src.get("matchSeconds")
                if anchor is None:
                    anchor = find_anchor(path, vid)
                    if anchor is not None:
                        src["matchSeconds"] = round(anchor, 1); sources_changed.add(vid)
                if anchor is None:
                    anchor = float(src.get("searchFrom", SKIP_SECONDS)) + 3
                frames, times = window_frames(path, float(anchor))
                if len(frames) < 3:
                    print("   no frames, skipped")
                    continue
                i, j = pick_pair(frames, times, float(anchor))
                fs, fe, s, e = frames[i], frames[j], times[i], times[j]
            results[vid] = {"name": name, "start": save(fs, f"{vid}-start.webp"),
                            "end": save(fe, f"{vid}-end.webp"), "t": [round(s, 1), round(e, 1)],
                            "file": os.path.basename(path)}
        except Exception as err:  # keep going if one video fails
            print("   failed:", err)
            missing.append((vid, name, str(err)))
            if kept:
                results[vid] = {"name": name, "start": kept[0], "end": kept[1],
                                "t": remembered.get(vid, {}).get("t", ["kept", "kept"]), "file": ""}
                print("   kept existing photos instead")

    json.dump({vid: {"name": r["name"], "t": r["t"], "file": r["file"]} for vid, r in results.items()},
              open(FRAMES, "w"), indent=1)
    if sources_changed:  # remember anchors worked out for hand-fixed sources
        allsrc = json.load(open(SOURCES))
        for vid in sources_changed:
            allsrc[vid]["matchSeconds"] = sources[vid]["matchSeconds"]
        json.dump(allsrc, open(SOURCES, "w"), indent=1)

    data = json.load(open(DATA))
    for g in data["groups"]:
        for w in g["workouts"]:
            for b in w["blocks"]:
                for ex in b["exercises"]:
                    r = results.get(ex.get("video"))
                    if r:
                        ex["startPhoto"], ex["endPhoto"] = r["start"], r["end"]
    json.dump(data, open(DATA, "w"), indent=1, ensure_ascii=False)

    rows = "".join(
        f'<div class="r" id="{vid}"><h3><span class="n">{i}</span> {r["name"]} <code>{vid}</code> '
        f'<small>{r["file"]} · {r["t"][0]}s → {r["t"][1]}s</small></h3>'
        f'<div class="pics"><figure><img src="../{r["start"]}" loading="lazy"><figcaption>Start</figcaption></figure>'
        f'<figure><img src="../{r["end"]}" loading="lazy"><figcaption>End</figcaption></figure></div></div>'
        for i, (vid, r) in enumerate(results.items(), 1))
    miss = "".join(f"<li>{name} <code>{vid}</code>: {err}</li>" for vid, name, err in missing)
    open(os.path.join(ROOT, "tools", "review.html"), "w").write(
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>YAE start and end photos</title><style>body{font:15px system-ui;margin:16px;max-width:1100px}"
        ".r{margin-bottom:26px;border-top:1px solid #ddd;padding-top:10px}.pics{display:grid;grid-template-columns:1fr 1fr;gap:8px}"
        "figure{margin:0;position:relative}img{width:100%;border-radius:8px}figcaption{position:absolute;left:8px;top:8px;background:#fff;"
        "padding:2px 6px;border-radius:4px;font-size:12px;font-weight:700}code{color:#d6307a}h3{font-size:16px;margin:0 0 8px}"
        ".n{display:inline-block;background:#111;color:#fff;border-radius:6px;padding:2px 7px;margin-right:6px}small{color:#666;font-weight:400}</style>"
        f"<h1>Check every pair ({len(results)})</h1><p>Left is the start position, right is the end. Tell me the number of any pair to redo "
        "and what it should show (for example '12: start is her setting up, use the second rep').</p>"
        + (f"<h2>Missing recordings</h2><ul>{miss}</ul>" if miss else "") + rows)
    print(f"\nDone: {len(results)} of {len(ids)} videos. {len(missing)} missing. Open tools/review.html to check them.")


if __name__ == "__main__":
    sys.exit(main())
