from fastapi import FastAPI
from app.routers import health, auth
from app.core.database import engine
from app.models.user import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SKN Backend")

app.include_router(health.router)
app.include_router(auth.router)
