"""
Transcribe the lesson recordings in tools/lessons/ with word timestamps.

    pip install faster-whisper
    python tools/transcribe.py            # every video not yet done
    python tools/transcribe.py "The Parent Playbook.MOV"

Writes tools/lessons/transcripts/<name>.json (segments with start, end, text and words)
and <name>.txt (readable, one line per segment with a timestamp). These feed the cut
list and the one-page summaries.
"""
import glob, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSONS = os.path.join(ROOT, "tools", "lessons")
OUT = os.path.join(LESSONS, "transcripts")
PRIORITY = ["The Parent Playbook.MOV", "The Parent Playbook -2.MOV"]


def audio_for(path):
    wav = os.path.join(OUT, os.path.splitext(os.path.basename(path))[0] + ".wav")
    if not os.path.exists(wav):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", "16000", "-vn", wav], check=True)
    return wav


def main():
    from faster_whisper import WhisperModel
    os.makedirs(OUT, exist_ok=True)
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(LESSONS, "*.[Mm][Oo][Vv]")))
    files = [os.path.join(LESSONS, f) if not os.path.isabs(f) else f for f in files]
    files.sort(key=lambda f: (os.path.basename(f) not in PRIORITY, PRIORITY.index(os.path.basename(f)) if os.path.basename(f) in PRIORITY else 0))
    model = WhisperModel("small", device="cpu", compute_type="int8")
    for path in files:
        base = os.path.splitext(os.path.basename(path))[0]
        jpath = os.path.join(OUT, base + ".json")
        if os.path.exists(jpath):
            print("have", base); continue
        print("transcribing", base, flush=True)
        wav = audio_for(path)
        # load the wav ourselves (the bundled audio decoder clashes with the installed 'av' version)
        import numpy as np, wave
        with wave.open(wav) as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        segs, info = model.transcribe(audio, language="en", word_timestamps=True, vad_filter=True,
                                      vad_parameters={"min_silence_duration_ms": 400})
        out = []
        for s in segs:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                        "words": [{"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)} for w in (s.words or [])]})
        json.dump({"file": os.path.basename(path), "duration": info.duration, "segments": out}, open(jpath, "w"), indent=1)
        with open(os.path.join(OUT, base + ".txt"), "w") as f:
            for s in out:
                m, sec = divmod(int(s["start"]), 60)
                f.write(f"[{m:02d}:{sec:02d}] {s['text']}\n")
        os.remove(wav)
        print(f"   {len(out)} segments, {info.duration/60:.1f} min", flush=True)


if __name__ == "__main__":
    sys.exit(main())
