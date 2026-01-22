# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**모든 응답은 한국어로 작성해야 합니다.** (All responses must be in Korean.)

## Project Overview

**상하의 (Sanghawi)** is a multi-agent AI platform for personalized fashion/outfit recommendations. It analyzes users' digital wardrobes and celebrity styles to provide outfit suggestions.

## Tech Stack

- **Backend**: FastAPI + Uvicorn, SQLAlchemy ORM, MySQL (PyMySQL), bcrypt for auth
- **Frontend**: Static HTML/CSS/JavaScript (jQuery-based)
- **AI/ML**: OpenAI GPT-4, LangGraph (multi-agent framework), LangChain, ChromaDB (vector DB for RAG)
- **Infrastructure**: Docker, AWS EC2 (planned)

## Commands

### Backend
```bash
# From project root
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd front
python -m http.server 8000
# Or open HTML files directly in browser
```

### Docker
```bash
docker-compose up -d
```

## Architecture

### Multi-Agent System
The project uses LangGraph to orchestrate three specialized agents:

1. **Celeb Agent** - Matches user wardrobe items with celebrity styles
2. **Wardrobe Analysis Agent** - Analyzes item utilization and recommends purchases
3. **Decision Orchestrator Agent** - Synthesizes recommendations from other agents

### Project Structure
```
backend/
  app/
    main.py           # FastAPI app initialization, creates DB tables
    core/
      config.py       # Pydantic settings (loads from .env)
      database.py     # SQLAlchemy engine/session setup
    models/           # SQLAlchemy ORM models
    routers/          # FastAPI route handlers

front/
  mainpage/           # Landing pages, login, FAQ
  smart_wardrobe/     # Wardrobe management UI, chatbot
  celeb's_pick/       # Celebrity style showcase
```

### Backend Pattern
- Routes are organized in `routers/` and included in `main.py`
- Database models in `models/` use SQLAlchemy declarative base
- Configuration via pydantic-settings loading from `.env`

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY` - OpenAI API key for GPT-4 and embeddings
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` - MySQL connection

## Korean Language

This is a Korean team project. Code comments, commit messages, and documentation may be in Korean. Feature names:
- Smart Wardrobe (스마트 옷장) - Digital closet management
- Celeb's Pick (셀럽 스타일) - Celebrity style matching
- AI Chatbot (코디 추천 챗봇) - Outfit recommendation chatbot
