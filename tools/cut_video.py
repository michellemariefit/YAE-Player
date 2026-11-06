"""
Render a trimmed lesson video from a cut list.

    python tools/cut_video.py "The Parent Playbook"

Reads tools/lessons/cuts/<name>.json ({"keep": [[start, end], ...]} in seconds) and the
recording in tools/lessons/, and writes tools/lessons/out/<name>.mp4: 1080p, H.264, AAC,
ready to upload to the GHL lesson. Each kept piece is encoded on its own (light on memory),
with a short audio fade at each join so the cuts do not click, then the pieces are joined.
Also writes <name>-chapters.txt with where each kept section starts in the new file.
"""
import json, os, shutil, subprocess, sys, tempfile

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
    tmp = tempfile.mkdtemp(prefix="cut-", dir=OUT)
    print("rendering", name, f"({len(keep)} pieces, {sum(b-a for a,b in keep)/60:.1f} min)", flush=True)
    pieces = []
    for i, (a, b) in enumerate(keep):
        piece = os.path.join(tmp, f"p{i:02d}.mp4")
        d = b - a
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", src,
                        "-vf", "scale=-2:1080", "-af", f"afade=t=in:d=0.08,afade=t=out:st={max(0, d-0.08):.3f}:d=0.08",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-threads", "2", piece], check=True)
        pieces.append(piece)
        print(f"   piece {i+1}/{len(keep)} done", flush=True)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for p in pieces:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(tmp)
    t = 0.0
    with open(os.path.join(OUT, name + "-chapters.txt"), "w") as f:
        for a, b in keep:
            f.write(f"{int(t)//60:02d}:{int(t)%60:02d}  (from {int(a)//60:02d}:{int(a)%60:02d} in the original)\n")
            t += b - a
    print("wrote", os.path.relpath(out, ROOT), f"{os.path.getsize(out)//2**20} MB", flush=True)


if __name__ == "__main__":
    for n in sys.argv[1:]:
        main(n)
