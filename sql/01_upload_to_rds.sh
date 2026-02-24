#!/bin/bash
# FTO 프로젝트 - RDS 데이터 업로드 스크립트
# 실행: bash sql/01_upload_to_rds.sh

set -e

# 설정
EC2_HOST="ubuntu@52.78.233.64"
EC2_KEY="~/Downloads/fto-key.pem"
RDS_HOST="fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com"
RDS_USER="admin"
RDS_DB="fto"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=========================================="
echo "FTO RDS 업로드 스크립트"
echo "=========================================="

# Step 1: 파일 EC2로 전송
echo ""
echo "[1/4] EC2로 파일 전송 중..."
scp -i $EC2_KEY "$PROJECT_DIR/sql/fto_schema.sql" $EC2_HOST:~/
scp -i $EC2_KEY "$PROJECT_DIR/claim_keywords_full.csv" $EC2_HOST:~/

echo "✅ 파일 전송 완료"

# Step 2: EC2에서 RDS 작업 실행
echo ""
echo "[2/4] RDS에 스키마 생성 중..."
echo "RDS 비밀번호를 입력하세요:"

ssh -i $EC2_KEY $EC2_HOST << 'ENDSSH'
# 스키마 생성
mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -p fto < ~/fto_schema.sql
echo "✅ 스키마 생성 완료"
ENDSSH

echo ""
echo "[3/4] claim_keywords CSV 데이터 로드 중... (약 1000만건, 시간 소요)"
echo "RDS 비밀번호를 다시 입력하세요:"

ssh -i $EC2_KEY $EC2_HOST << 'ENDSSH'
mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -p --local-infile=1 fto << 'ENDMYSQL'
SET GLOBAL local_infile = 1;
LOAD DATA LOCAL INFILE '/home/ubuntu/claim_keywords_full.csv'
INTO TABLE claim_keywords
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(patent_id, chunk_id, keyword);
SELECT COUNT(*) as 'claim_keywords 건수' FROM claim_keywords;
ENDMYSQL
ENDSSH

echo ""
echo "[4/4] EC2 임시 파일 정리..."
ssh -i $EC2_KEY $EC2_HOST "rm -f ~/fto_schema.sql ~/claim_keywords_full.csv"

echo ""
echo "=========================================="
echo "✅ 업로드 완료!"
echo "=========================================="
echo ""
echo "로컬 CSV 삭제하려면:"
echo "rm $PROJECT_DIR/claim_keywords_full.csv"
