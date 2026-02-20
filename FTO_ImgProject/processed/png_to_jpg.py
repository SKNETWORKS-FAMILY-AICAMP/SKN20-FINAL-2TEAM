from PIL import Image
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sketch_dir = str(PROJECT_ROOT / "data/photo")
output_dir = str(PROJECT_ROOT / "data/sketch/images_v2")

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(sketch_dir):
    if filename.lower().endswith(".png"):
        png_path = os.path.join(sketch_dir, filename)
        jpg_path = os.path.join(output_dir, os.path.splitext(filename)[0] + ".jpg")
        
        img = Image.open(png_path).convert("RGB")
        img.save(jpg_path, "JPEG", quality=95)
        print(f"변환 완료: {filename} -> {os.path.basename(jpg_path)}")

print(f"모든 변환이 완료되었습니다. 저장 위치: {output_dir}/")