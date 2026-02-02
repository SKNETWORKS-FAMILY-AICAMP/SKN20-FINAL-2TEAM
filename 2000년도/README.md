# 2000년도 디자인 특허 데이터 작업 요약

## 개요
2000년도 KIPRIS 디자인 특허 데이터를 기반으로 **XML → JSON 변환**, **이미지/텍스트 벡터화**, **유사도 분석**을 수행한 결과와 스크립트를 정리한 폴더입니다. CLIP/OpenCLIP 파이프라인, 유사도 결과 CSV, 임베딩 파일, 이미지 다운로드 결과, 그리고 분석 보고서가 포함됩니다.

## 폴더 구성
- `2000_xml/`: 원본 XML 데이터
- `2000_json/`: XML에서 변환된 JSON (도면 단위)
- `2000_raw_data/`: 수집 원본/중간 산출물
- `img/`: 다운로드된 디자인 이미지
- `split_output/`: JSONL 분리 결과(문서/메타데이터)
- `chroma_openclip/`: OpenCLIP 임베딩의 ChromaDB 저장소(옵션)

## 주요 스크립트
- `2000_xml_to_json.py`: XML → JSON 변환
- `2000img_extraction.py`: 이미지 다운로드/추출
- `clip_vector_similarity.py`: CLIP 기반 벡터화 및 유사도 계산
- `openclip_vector_similarity_v1.py`: OpenCLIP 임베딩 생성 (이미지+텍스트 동일 공간)
- `openclip_vector_similarity_v2.py`: OpenCLIP 기반 이미지-이미지 유사도 비교
- `Split_jsonl.py`: JSONL을 문서/메타데이터로 분리

## 핵심 산출물
- `09-01_2000_vectors.pkl`: CLIP 벡터 DB
- `09-01_2000_similarity_results.csv`: CLIP 유사도 결과
- `Openclip_similarity_results.csv`: OpenCLIP 유사도 결과
- `openclip_embeddings.npz`: OpenCLIP 임베딩
- `openclip_metadata.jsonl`: OpenCLIP 메타데이터
- `split_output/documents.jsonl`, `split_output/metadata.csv`: 분리된 데이터

## 참고 문서/보고서
- `CLIP_README.md`: CLIP 파이프라인 상세 가이드
- `OPENCLIP_README.md`: OpenCLIP 임베딩 파이프라인 상세
- `OpenCLIP 이미지 유사도 비교_README.md`: 이미지 유사도 비교 사용법
- `AI_기반_FTO_검토_보고서.pdf`
- `FTO_googleIMG_TEST_보고서.pdf`
- `FTO_minji_01_TEST_보고서.pdf`
- `FTO_minji_02_TEST_보고서.pdf`
- `FTO_minji_03_TEST_보고서.pdf`
- `FTO_조사대상디자인_TEST_보고서.pdf`
- `디자인 침해 위험 분석_TEST.pdf`
- `디자인_침해_위험_분석_TEST.docx`
- `minji_03_FTO_분석_보고서.docx`

## 빠른 시작
1. XML → JSON 변환: `2000_xml_to_json.py`
2. 이미지 다운로드: `2000img_extraction.py`
3. CLIP 유사도 분석: `clip_vector_similarity.py`
4. OpenCLIP 임베딩/유사도 분석: `openclip_vector_similarity_v1.py`, `openclip_vector_similarity_v2.py`

각 스크립트의 상세 옵션/설명은 위 README 문서들을 참고하세요.
