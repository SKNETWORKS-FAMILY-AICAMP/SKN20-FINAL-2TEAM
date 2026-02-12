from app.models.user import User
from app.models.chat import Chat, Message
from app.models.analysis import (
    Analysis,
    AnalysisImage,
    AnalysisKeyword,
    ImageMatch,
    ClaimMatch
)
from app.models.patent import (
    DesignPatent,
    Patent,
    Claim,
    PatentIPC,
    ClaimElement
)
# TODO: 디자인/RAG 팀 연동 후 활성화
# from app.models.patent import DesignEmbedding, ClaimEmbedding

__all__ = [
    "User",
    "Chat",
    "Message",
    "Analysis",
    "AnalysisImage",
    "AnalysisKeyword",
    "ImageMatch",
    "ClaimMatch",
    "DesignPatent",
    "Patent",
    "Claim",
    "PatentIPC",
    "ClaimElement",
]
