import os

path = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\images_2"
files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
print(f"파일 수: {len(files)}")
