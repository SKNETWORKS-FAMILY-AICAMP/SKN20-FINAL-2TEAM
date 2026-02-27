import os
import sys
import traceback
root = r"c:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM"
sys.path.insert(0, os.path.join(root, "design", "src"))
try:
    import design_chatbot
    print("import ok")
except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()
