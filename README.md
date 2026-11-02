# The Youth Athlete Edge workout player

One mobile web page that replaces the workout PDFs, plus a printable version of every workout.
Built from the Fit Mom To Be player and changed for how YAE is sold: no phases, no gym/home
split, one page per workout, language for athletes and the parents running the session.

## What's here

- `index.html` is the player. Pick a workout, tick each set, a rest timer appears inside the card.
- `print.html` is the printable version: one landscape page per workout, every exercise with its
  start and end photo, sets, reps and rest in a box at the top. Ink-light, prints fine in black and white.
- `data/yae.json` holds the whole program: six groups (Warm-Up, Mobility, Stretching, MAT Holds,
  Stability & Balance, Foundation Strength), 19 workouts, every exercise with its name, note,
  YouTube demo ID and photos. The player and the print page both read this one file, so they can
  never drift apart.
- `images/` holds the start and end photos pulled from the original recordings, plus the single
  photo from each PDF as a fallback (`*-pdf.webp`).
- `pdf/` holds a ready-made PDF of every workout, for the GHL resource section.

## Links

The page is live at `https://michellemariefit.github.io/yae-player/`.

| Link ends with | Shows |
| --- | --- |
| nothing | every group and workout, with pickers |
| `#foundation` | the eight Foundation workouts with a picker (same for `#stability`) |
| `#foundation-1` | only Foundation Workout 1, no pickers (same for `#stability-4`, `#warmup`, `#mobility`, `#stretching`, `#mat`) |

The print page works the same way: `print.html#foundation-1` is one page, `print.html` is all 19.

## Put it in GHL

Paste this in a lesson, changing the bit after `#` to the workout that lesson is about:

```html
<iframe src="https://michellemariefit.github.io/yae-player/#foundation-1" style="width:100%;height:1400px;border:0" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe>
```

A link with a workout name after `#` shows only that workout. A group name shows the picker for
that group. No `#` shows everything.

## Rebuild the data from the PDFs

`tools/build_workouts.py` reads the workout PDFs and writes `data/yae.json`. Put the PDFs from
Dropbox in `tools/pdf/` (ignored by git) named `warmup.pdf`, `stretching.pdf`, `mat.pdf`,
`mobility.pdf`, `stability-1.pdf` to `stability-6.pdf`, `foundation-1.pdf` to `foundation-8.pdf`:

```
pip install pymupdf pillow
python tools/build_workouts.py
```

It keeps any start and end photos that were already added. Group names and intros live in the
`GROUPS` table at the top of the script.

## Start and end photos

The photos come from the original recordings in Dropbox, folder
`PRODUCTS & PROGRAMS / The Youth Athlete Edge / Videos / Workouts`.

- `tools/sources.json` maps each YouTube demo ID to its recording. `tools/match_sources.py` built it
  by matching the photo in each PDF against every recording; entries marked `locked` were fixed by hand.
- Copy the recordings into `tools/cache/` (ignored by git), then run
  `pip install opencv-python-headless numpy` and `python tools/grab_frames.py`.
- It picks the frame just before the first rep starts as the start, and the most different frame
  within that rep as the end.
- Check every pair in `tools/review.html`. Fix any wrong pair by adding the exact seconds to
  `tools/overrides.json` and running the script again. `tools/frames.json` remembers the seconds used.
- Photos that already exist in `images/` are kept. To redo one on purpose:
  `python tools/grab_frames.py --force <video id>`.

## Printable PDFs

`tools/make_pdfs.py` opens `print.html` in headless Chromium and writes one PDF per workout plus
`pdf/yae-all-workouts.pdf`. Run it after the photos change:

```
python tools/make_pdfs.py
```

## Instruction videos

The module videos are uploaded straight into the GHL lessons (not YouTube), so the player does not
embed them. The lesson plays the video above the iframe.
