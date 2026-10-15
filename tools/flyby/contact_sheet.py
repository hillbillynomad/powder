"""Contact sheet of the map area of review stills, labelled with their loop time.

usage: python tools/flyby/contact_sheet.py <stills dir> <out.png> [columns=3]
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

shots = sorted(glob.glob(os.path.join(sys.argv[1], 't*.png')))
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
W, H = 480, 370  # map area (960x740 crop) at half size
rows = (len(shots) + cols - 1) // cols
sheet = Image.new('RGB', (W * cols, H * rows), 'black')
for i, p in enumerate(shots):
    im = Image.open(p).convert('RGB').crop((320, 60, 1280, 800)).resize((W, H))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 70, 22), fill='black')
    d.text((6, 5), os.path.basename(p)[1:-4] + ' s', fill='white')
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(sys.argv[2])
print(sys.argv[2])
