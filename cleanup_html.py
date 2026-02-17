import re
import os

filepath = r'c:\youtubehabit\index.html'
with open(filepath, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace the broken videos array with an empty one
new_html = re.sub(r'const videos = \[.*?\];', 'const videos = [];', html, flags=re.DOTALL)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_html)
print("Index.html cleaned up.")
