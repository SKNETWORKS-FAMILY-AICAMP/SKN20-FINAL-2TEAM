"""공통 로깅 설정 (loguru).

사용법:
    from app.logger import logger
"""

import sys
from pathlib import Path
from loguru import logger

# 기본 핸들러 제거 후 재설정
logger.remove()

# stdout (터미널 + Docker 캡처)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    level="INFO",
    colorize=True,
)

# 파일 (10MB 로테이션, 30일 보관)
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger.add(
    LOG_DIR / "fto.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8",
)
