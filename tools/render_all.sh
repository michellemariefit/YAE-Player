#!/bin/bash
# Render every cut list that has no finished MP4 yet, one at a time. Safe to re-run after a restart.
cd "$(dirname "$0")/.."
rm -rf tools/lessons/out/cut-*
for c in tools/lessons/cuts/*.json; do
  n=$(basename "$c" .json)
  [ -s "tools/lessons/out/$n.mp4" ] && { echo "have $n"; continue; }
  python3 -I tools/cut_video.py "$n" || echo "FAILED $n"
done
echo ALL DONE
