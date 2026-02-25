# langchain 환경에서 실행
# design/src/ 위치에서

from design_chatbot import run_chatbot, graph

# TC-1: 이미지
result = run_chatbot(image_path=r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\images\3019810003379-api_xml-1_001.JPG")

# TC-2: 일반 질문
result = run_chatbot(text_query="디자인 특허 출원 절차가 뭐야?")

# TC-3: DB 검색
result = run_chatbot(text_query="펌프형 용기 디자인 찾아줘")

# TC-4: 웹 검색
result = run_chatbot(text_query="2024년 디자인 특허 출원 통계 알려줘")