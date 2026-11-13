#!/usr/bin/env bash
# Encode the web versions of the film from a folder of master frames (16-bit or 8-bit PNG).
# Usage: tools/encode_web.sh <frames_dir> <version, e.g. v2> [out_dir] [first_frame]
# Output (all silent, metadata stripped):
#   software-factory-<v>-av1.mp4   AV1 10-bit (Chrome, Edge, Firefox, Safari on M3/A17+)  - first <source>
#   software-factory-<v>-hevc.mp4  HEVC 10-bit, hvc1 tag (Safari on older Apple devices)  - second
#   software-factory-<v>.mp4       H.264 8-bit (everything else)                           - fallback
# 10-bit keeps the dusk sky and dark interior free of banding; 16-bit PNG masters feed it directly.
set -euo pipefail
FR=${1:?frames dir}; V=${2:?version}; OUT=${3:-renders/web}; START=${4:-73}
mkdir -p "$OUT"
IN=(-start_number "$START" -framerate 24 -i "$FR/f_%04d.png")
SCALE=${SCALE:-}                       # e.g. SCALE=2560:1440 to downscale a 4K master (lanczos)
VF="format=rgb48le"
[ -n "$SCALE" ] && VF="$VF,scale=$SCALE:flags=lanczos+accurate_rnd+full_chroma_int"
COMMON=(-an -map_metadata -1 -fflags +bitexact -movflags +faststart -g 48)

ffmpeg -v error -stats -y "${IN[@]}" -vf "$VF" -c:v libsvtav1 -pix_fmt yuv420p10le -crf "${AV1_CRF:-22}" -preset 3 \
  -svtav1-params tune=0:enable-variance-boost=1 "${COMMON[@]}" "$OUT/software-factory-$V-av1.mp4"
ffmpeg -v error -stats -y "${IN[@]}" -vf "$VF" -c:v libx265 -pix_fmt yuv420p10le -crf "${HEVC_CRF:-19}" -preset slow \
  -tag:v hvc1 -x265-params log-level=error "${COMMON[@]}" "$OUT/software-factory-$V-hevc.mp4"
ffmpeg -v error -stats -y "${IN[@]}" -vf "$VF" -c:v libx264 -pix_fmt yuv420p -crf "${H264_CRF:-17}" -preset slower \
  -profile:v high "${COMMON[@]}" "$OUT/software-factory-$V.mp4"

for f in "$OUT"/software-factory-"$V"*.mp4; do
  printf '%s  %s bytes  ' "$f" "$(stat -f %z "$f")"
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,pix_fmt,bit_rate -of csv=p=0 "$f"
done
