#!/bin/bash
# concatena segmentos, muxa áudio e gera brag.mp4 (frame 0 = pôster, já embutido pelo render)
set -e
cd "$(dirname "$0")"
rm -f list.txt
for f in seg/seg_0.mp4 seg/seg_1.mp4 seg/seg_2.mp4 seg/seg_3.mp4; do echo "file '$f'" >> list.txt; done
ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -c copy video_all.mp4
ffmpeg -y -loglevel error -i video_all.mp4 -i mix.wav -map 0:v:0 -map 1:a:0 -c:v copy \
  -af "alimiter=limit=0.89:level=disabled" -c:a aac -b:a 192k -ar 44100 -movflags +faststart -shortest ../brag.mp4
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate,nb_frames -of default=nw=1 ../brag.mp4
