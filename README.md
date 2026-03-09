![header](https://capsule-render.vercel.app/api?type=waving&color=gradient&height=300&section=header&text=GEUNG%20MA%20&fontSize=60)
# 🔍 FTO 중심 특허·디자인 침해 리스크 판단 AI 에이전트

**개발기간:** 2026.01.09 ~ 2026.03.11  
**팀명:** 긍마
**프로젝트명:** FTO(Freedom to Operate) 특허 리스크 분석 시스템  


## 📌 프로젝트 개요

제품 출시 전 "타인의 특허/디자인을 침해하지 않는가?"라는 실무적 질문에 답하는 AI 기반 FTO 판단 서비스입니다.

**핵심 질문:**
> "이 제품을 출시해도 특허 침해 리스크가 없을까?"

## 🎯 핵심 기술 스택

**AI/ML:**
- RAG (Retrieval-Augmented Generation)
- SBERT (Sentence-BERT) for Embeddings
- OpenAI GPT-4 (답변 검증)
- CLIP (디자인 이미지 임베딩)
- Small LLM (침해 판단 모델)

**데이터베이스:**
- MySQL 8.4 (AWS RDS, 메타데이터 관리)
- ChromaDB / Pinecone (Vector Database)

**프레임워크:**
- LangChain (RAG 파이프라인)
- FastAPI / Django (백엔드 API)
- Streamlit (프로토타입 UI)

**데이터 출처:**
- KIPRIS (한국특허정보원) 공공 데이터
  - 특허/실용신안 공개·등록공보 XML
  - 청구항 변동이력 XML
  - 디자인 공보 XML
  - 디자인 의견제출통지서 PDF

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-Latest-green.svg)](https://www.langchain.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)](https://openai.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.4-4479A1.svg)](https://www.mysql.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Latest-purple.svg)](https://www.trychroma.com/)
