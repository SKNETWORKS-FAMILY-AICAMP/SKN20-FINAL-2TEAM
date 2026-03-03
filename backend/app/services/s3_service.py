"""S3 이미지 업로드/삭제 서비스.

디자인 분석 세션의 이미지를 S3에 저장하고 Public URL을 반환합니다.
"""
import uuid
from datetime import datetime
from typing import Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from app.config import settings


class S3Service:
    """S3 이미지 업로드/삭제 서비스."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy initialization of S3 client."""
        if self._client is None:
            if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
                raise RuntimeError(
                    "AWS 자격 증명이 설정되지 않았습니다. "
                    ".env 파일에 AWS_ACCESS_KEY_ID와 AWS_SECRET_ACCESS_KEY를 설정하세요."
                )
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
        return self._client

    def upload_image(
        self,
        file_bytes: bytes,
        session_id: str,
        filename: Optional[str] = None,
        content_type: str = "image/jpeg",
    ) -> Tuple[str, str]:
        """
        이미지를 S3에 업로드합니다.

        Args:
            file_bytes: 이미지 바이트 데이터
            session_id: 디자인 세션 ID (thread_id)
            filename: 원본 파일명 (선택)
            content_type: MIME 타입 (기본: image/jpeg)

        Returns:
            (s3_key, s3_url) 튜플
        """
        # S3 키 생성: design-sessions/{session_id}/{timestamp}_{uuid}.jpg
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        extension = self._get_extension(filename, content_type)
        s3_key = f"{settings.S3_DESIGN_PREFIX}{session_id}/{timestamp}_{unique_id}{extension}"

        try:
            self.client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                Body=file_bytes,
                ContentType=content_type,
            )

            # Public URL 생성
            s3_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

            print(f"[S3] 업로드 성공: {s3_key}")
            return s3_key, s3_url

        except ClientError as e:
            print(f"[S3] 업로드 실패: {e}")
            raise RuntimeError(f"S3 업로드 실패: {e}")

    def delete_image(self, s3_key: str) -> bool:
        """
        S3에서 이미지를 삭제합니다.

        Args:
            s3_key: 삭제할 S3 객체 키

        Returns:
            삭제 성공 여부
        """
        try:
            self.client.delete_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
            )
            print(f"[S3] 삭제 성공: {s3_key}")
            return True
        except ClientError as e:
            print(f"[S3] 삭제 실패: {e}")
            return False

    def delete_session_images(self, session_id: str) -> int:
        """
        세션의 모든 이미지를 삭제합니다.

        Args:
            session_id: 디자인 세션 ID (thread_id)

        Returns:
            삭제된 객체 수
        """
        prefix = f"{settings.S3_DESIGN_PREFIX}{session_id}/"
        deleted_count = 0

        try:
            # 세션 prefix 아래의 모든 객체 목록 조회
            response = self.client.list_objects_v2(
                Bucket=settings.S3_BUCKET_NAME,
                Prefix=prefix,
            )

            if "Contents" not in response:
                return 0

            # 각 객체 삭제
            for obj in response["Contents"]:
                if self.delete_image(obj["Key"]):
                    deleted_count += 1

            print(f"[S3] 세션 이미지 삭제 완료: {session_id} ({deleted_count}개)")
            return deleted_count

        except ClientError as e:
            print(f"[S3] 세션 이미지 삭제 실패: {e}")
            return deleted_count

    def _get_extension(
        self, filename: Optional[str], content_type: str
    ) -> str:
        """파일 확장자를 결정합니다."""
        if filename:
            parts = filename.rsplit(".", 1)
            if len(parts) > 1:
                return f".{parts[-1].lower()}"

        # content_type으로 추론
        type_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        return type_map.get(content_type, ".jpg")

    def check_connection(self) -> bool:
        """S3 연결 상태를 확인합니다."""
        try:
            self.client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            return True
        except ClientError:
            return False


# 싱글톤 인스턴스
s3_service = S3Service()
