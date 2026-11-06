"""
Render a trimmed lesson video from a cut list.

    python tools/cut_video.py "The Parent Playbook"

Reads tools/lessons/cuts/<name>.json ({"keep": [[start, end], ...]} in seconds) and the
recording in tools/lessons/, and writes tools/lessons/out/<name>.mp4: 1080p, H.264, AAC,
ready to upload to the GHL lesson. Hard cuts with a 4-frame audio crossfade so the joins
do not click. Also writes <name>-chapters.txt with the timestamps of each kept section.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSONS = os.path.join(ROOT, "tools", "lessons")
CUTS = os.path.join(LESSONS, "cuts")
OUT = os.path.join(LESSONS, "out")


def main(name):
    spec = json.load(open(os.path.join(CUTS, name + ".json")))
    src = os.path.join(LESSONS, spec["source"])
    keep = [k for k in spec["keep"] if k[1] - k[0] > 0.3]
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, name + ".mp4")
    # filter graph: trim each kept piece, then concatenate
    parts, fc = [], []
    for i, (a, b) in enumerate(keep):
        fc.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,scale=-2:1080[v{i}];"
                  f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,afade=t=in:d=0.08,afade=t=out:st={max(0, b-a-0.08)}:d=0.08[a{i}]")
        parts.append(f"[v{i}][a{i}]")
    fc.append("".join(parts) + f"concat=n={len(keep)}:v=1:a=1[v][a]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats", "-i", src, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", out]
    print("rendering", name, f"({len(keep)} pieces, {sum(b-a for a,b in keep)/60:.1f} min)")
    subprocess.run(cmd, check=True)
    t = 0.0
    with open(os.path.join(OUT, name + "-chapters.txt"), "w") as f:
        for a, b in keep:
            f.write(f"{int(t)//60:02d}:{int(t)%60:02d}  (from {int(a)//60:02d}:{int(a)%60:02d} in the original)\n")
            t += b - a
    print("wrote", os.path.relpath(out, ROOT), f"{os.path.getsize(out)//2**20} MB")


if __name__ == "__main__":
    for n in sys.argv[1:]:
        main(n)
