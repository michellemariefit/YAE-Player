"""
Build data/yae.json from the Youth Athlete Edge workout PDFs.

    pip install pymupdf pillow
    python tools/build_workouts.py

Put the PDFs from Dropbox (PRODUCTS & PROGRAMS / The Youth Athlete Edge / PDF's)
in tools/pdf/ (ignored by git) with these names:

    warmup.pdf  stretching.pdf  mat.pdf  mobility.pdf
    stability-1.pdf ... stability-6.pdf
    foundation-1.pdf ... foundation-8.pdf

Each PDF is one workout: a header ("How to do it: 2-3 sets · 15-20 reps ... rest 60
seconds"), then one row per exercise with a code (A1, B2 or 1, 2, 3), a name that links to
the YouTube demo, an optional note ("Finish each set with 10 pulses") and an optional
progression link. The photo in each row is saved as images/<video id>-pdf.webp and used
until grab_frames.py makes the start and end pair.

What it writes: data/yae.json, one file for the whole program:
  groups[]            Warm-Up, Stretching, MAT Holds, Mobility, Stability, Foundation
    workouts[]        one per PDF
      blocks[]        lettered groups (A, B) done back to back; numbered workouts get one
                      block per exercise
        exercises[]   code, name, video, note, photo, (startPhoto, endPhoto)
"""
import io, json, os, re, sys
import pymupdf
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "tools", "pdf")
IMAGES = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "data", "yae.json")

# Program structure. Order here is the order in the player.
GROUPS = [
    {"id": "warmup", "name": "Warm-Up", "files": ["warmup"],
     "intro": "Before every game, and before practice when there's time. Short on time? Pick 3 to 5 of these.",
     "when": "Before every game, no exceptions. Before practice too when there is time. Short on time? Pick 3 to 5 of the exercises."},
    {"id": "mobility", "name": "Mobility", "files": ["mobility"],
     "intro": "5 to 10 minutes. Before or after practice, or on an off day.",
     "when": "2 to 3 times a week, 5 to 10 minutes. In season: before practice on practice days. Off season: on off days or your own training day. This is not a workout, it attaches to one."},
    {"id": "stretching", "name": "Stretching", "files": ["stretching"],
     "intro": "After practice, after games, or on off days. Always finish with the MAT holds so the muscles wake back up.",
     "when": "Recovery, 2 to 3 times a week, 5 to 10 minutes. After practice, after a game, or on an off day. Always finish with the MAT Holds."},
    {"id": "mat", "name": "MAT Holds", "files": ["mat"],
     "intro": "Do these right after stretching. Stretching relaxes the muscles; these turn them back on.",
     "when": "Right after stretching, every time. Stretching relaxes the muscles; these turn them back on."},
    {"id": "stability", "name": "Stability & Balance", "files": [f"stability-{n}" for n in range(1, 7)],
     "intro": "Off-season: 2 a week. In season: 1 a week still helps. Master the Disc version before moving up to the BOSU.",
     "when": "In season: 1 workout a week, this or a Foundation workout. Off season: 2 workouts a week, one Stability and one Foundation. Never the day before a game."},
    {"id": "foundation", "name": "Foundation Strength", "files": [f"foundation-{n}" for n in range(1, 9)],
     "intro": "Off-season: 2 a week. In season: 1 a week. Swap in a Stability exercise or two any time.",
     "when": "In season: 1 workout a week, this or a Stability workout. Off season: 2 workouts a week, one Foundation and one Stability. Never the day before a game. Work through the eight in order."},
]
TITLE_FIX = {"warmup": "Warm-Up", "mat": "MAT Holds"}
YT = re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})")


def yt(uri):
    m = YT.search(uri or "")
    return m.group(1) if m else None


def parse_header(lines):
    """Pull sets, reps and rest out of the 'How to do it' line."""
    text = " ".join(lines)
    how = re.search(r"How to do it:\s*(.*?)(?:Make it yours:|When to do it:|Tap any|$)", text, re.S)
    when = re.search(r"When to do (?:this|it):\s*(.*?)(?:How to do it:|Tap any|Pair it|$)", text, re.S)
    tip = re.search(r"Make it yours:\s*(.*?)$", text, re.S)
    how = (how.group(1) if how else "").strip(" ·")
    m = re.search(r"(\d+)(?:-(\d+))?\s*sets?", how)
    sets_lo, sets_hi = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (1, 1)
    r = re.search(r"(\d+(?:-\d+)?)\s*reps?", how)
    rest = re.search(r"rest\s*(\d+)(?:-(\d+))?\s*seconds?", how)
    return {
        "how": re.sub(r"\s+", " ", how).replace("Tap any picture or name to watch the video demo.", "").strip(" ·"),
        "when": re.sub(r"\s+", " ", when.group(1)).strip(" ·") if when else "",
        "tip": re.sub(r"\s+", " ", tip.group(1)).strip() if tip else "",
        "setsMin": sets_lo, "sets": sets_hi,
        "reps": r.group(1) if r else "",
        "restSeconds": int(rest.group(2) or rest.group(1)) if rest else 0,
        "restLabel": (rest.group(1) + ("-" + rest.group(2) if rest.group(2) else "") + "s") if rest else "",
    }


def parse_pdf(path):
    doc = pymupdf.open(path)
    title, header, exercises, section = "", [], [], ""
    for page in doc:
        links = [(pymupdf.Rect(l["from"]), yt(l.get("uri"))) for l in page.get_links() if yt(l.get("uri"))]
        images = [(pymupdf.Rect(i["bbox"]), i["xref"]) for i in page.get_image_info(xrefs=True) if i["xref"]]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1]), b[0]))
        cur = None
        for b in blocks:
            if b[6] != 0:
                continue
            r = pymupdf.Rect(b[:4])
            lines = [re.sub(r"[ \t]+", " ", x).strip() for x in b[4].split("\n")]
            lines = [x for x in lines if x]
            if not lines or lines[-1].startswith("The Youth Athlete Edge ·"):
                continue
            if lines[0].startswith("T H E"):
                if page.number == 0 and len(lines) > 1:
                    title = " ".join(lines[1:])
                continue
            vids = [v for (lr, v) in links if lr.intersects(r)]
            if re.fullmatch(r"[A-Z]\d|\d{1,2}", lines[0]):
                cur = {"code": lines[0], "name": " ".join(lines[1:]), "video": vids[0] if vids else None,
                       "note": "", "alts": [], "y": r.y0, "section": section}
                exercises.append(cur)
                continue
            if re.fullmatch(r"[A-Z /&]+", lines[0]) and len(lines[0]) > 6:  # OPTIONAL / INTERCHANGEABLE
                section = lines[0].title()
                continue
            if cur is None:
                header.append(" ".join(lines))
                continue
            if not cur["name"] and not lines[0].startswith("▶"):  # name in its own block (MAT holds)
                cur["name"], cur["video"] = lines[0], (vids[0] if vids else cur["video"])
                lines = lines[1:]
            for line in lines:
                if line.startswith("▶"):
                    for part in re.split(r"\s*·\s*", line.lstrip("▶ ").strip()):
                        label = part.replace("Progression:", "").strip()
                        if not label or part.startswith("Watch the video"):
                            continue
                        alt = [v for v in vids if v != cur["video"]]
                        if alt:
                            cur["alts"].append({"label": label, "video": alt[-1]})
                else:
                    cur["note"] = (cur["note"] + " " + line).strip()
        for ex in [e for e in exercises if e.get("page") is None]:
            ex["page"] = page.number
            best = min(images, key=lambda im: abs(im[0].y0 - ex["y"]), default=None)
            if best and abs(best[0].y0 - ex["y"]) < 90 and ex["video"]:
                out = os.path.join(IMAGES, f"{ex['video']}-pdf.webp")
                if not os.path.exists(out):
                    raw = doc.extract_image(best[1])["image"]
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    im.thumbnail((720, 720))
                    im.save(out, "WEBP", quality=82)
                ex["photo"] = "images/" + os.path.basename(out)
    for ex in exercises:
        ex.pop("y", None); ex.pop("page", None)
        ex["note"] = re.sub(r"\s+", " ", ex["note"])
    return title, header, exercises


def build_workout(file_id, group):
    path = os.path.join(PDF, file_id + ".pdf")
    title, header, exercises = parse_pdf(path)
    meta = parse_header(header)
    lettered = all(re.fullmatch(r"[A-Z]\d", e["code"]) for e in exercises)
    blocks = []
    if lettered:
        for e in exercises:
            letter = e["code"][0]
            if not blocks or blocks[-1]["label"] != letter:
                blocks.append({"label": letter, "exercises": []})
            blocks[-1]["exercises"].append(e)
    elif meta["restSeconds"] > 0:
        # numbered workouts with a rest (Stability) are one circuit: do all of them, then rest
        blocks.append({"label": "Circuit", "exercises": list(exercises)})
    else:
        for e in exercises:
            blocks.append({"label": e["code"], "exercises": [e]})
    for e in exercises:
        if not e["alts"]:
            e.pop("alts")
        if not e.get("section"):
            e.pop("section", None)
    sets_label = (f"{meta['setsMin']} or {meta['sets']} sets" if meta["setsMin"] != meta["sets"]
                  else f"{meta['sets']} set" + ("s" if meta["sets"] != 1 else ""))
    return {"id": file_id, "name": TITLE_FIX.get(file_id, title), "group": group["id"],
            "how": meta["how"], "when": meta["when"], "tip": meta["tip"],
            "sets": meta["sets"], "setsLabel": sets_label, "reps": meta["reps"],
            "restSeconds": meta["restSeconds"], "restLabel": meta["restLabel"],
            "circuit": lettered or meta["restSeconds"] > 0, "blocks": blocks}


SWAPS = os.path.join(ROOT, "tools", "swaps.json")


def add_swaps(data):
    """Attach the Stability substitute (from tools/swaps.json) to each Foundation exercise."""
    if not os.path.exists(SWAPS):
        return
    swaps = {k: v for k, v in json.load(open(SWAPS)).items() if not k.startswith("_")}
    by_video = {}
    for g in sorted(data["groups"], key=lambda g: g["id"] != "stability"):   # prefer the Stability copy
        for w in g["workouts"]:
            for b in w["blocks"]:
                for e in b["exercises"]:
                    by_video.setdefault(e["video"], {**e, "from": w["name"]})
    n = 0
    for g in data["groups"]:
        for w in g["workouts"]:
            table = swaps.get(w["id"])
            if not table:
                continue
            for b in w["blocks"]:
                for e in b["exercises"]:
                    pick = table.get(e["code"])
                    if not pick:
                        continue
                    src = by_video.get(pick["video"])
                    if not src:
                        print("   swap not found for", w["id"], e["code"], pick["video"])
                        continue
                    e["swap"] = {k: src[k] for k in ("name", "video", "photo", "startPhoto", "endPhoto", "note", "alts", "from") if src.get(k)}
                    if pick.get("default"):
                        e["swap"]["default"] = True
                    n += 1
    print(f"{n} stability swaps attached")


def main():
    os.makedirs(IMAGES, exist_ok=True)
    data = {"program": "YAE", "name": "The Youth Athlete Edge", "groups": []}
    existing = {}
    if os.path.exists(OUT):  # keep start/end photos grab_frames.py already added
        for g in json.load(open(OUT))["groups"]:
            for w in g["workouts"]:
                for b in w["blocks"]:
                    for e in b["exercises"]:
                        if e.get("startPhoto"):
                            existing[e["video"]] = (e["startPhoto"], e["endPhoto"])
    n = 0
    for g in GROUPS:
        group = {"id": g["id"], "name": g["name"], "intro": g["intro"], "when": g["when"], "workouts": []}
        for f in g["files"]:
            w = build_workout(f, g)
            for b in w["blocks"]:
                for e in b["exercises"]:
                    n += 1
                    if e["video"] in existing:
                        e["startPhoto"], e["endPhoto"] = existing[e["video"]]
            group["workouts"].append(w)
            print(f"{w['id']}: {w['name']} · {sum(len(b['exercises']) for b in w['blocks'])} exercises · "
                  f"{w['setsLabel']} · {w['reps']} reps · rest {w['restLabel'] or 'none'}")
        data["groups"].append(group)
    add_swaps(data)
    json.dump(data, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"\n{n} exercise slots -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
