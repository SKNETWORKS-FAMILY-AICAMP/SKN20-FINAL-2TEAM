"""
전체 디자인 특허 벡터화 및 CSV 출력 (Mac MPS 지원)
- 4371개 전체 JSON/이미지를 벡터화
- 랜덤 쌍 비교 후 CSV 저장

label = 1: 유사함 (침해 가능성 높음)
label = 0: 유사하지 않음 (침해 가능성 낮음)
"""

import json
import os
import pickle
import csv
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
from tqdm import tqdm

import torch
from transformers import CLIPProcessor, CLIPModel
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

import requests
from PIL import Image
from io import BytesIO
import re
import time


def get_device():
    """Mac MPS / CUDA / CPU 자동 감지"""
    if torch.backends.mps.is_available():
        return 'mps'
    elif torch.cuda.is_available():
        return 'cuda'
    else:
        return 'cpu'


class DesignVectorDB:
    """디자인 특허 벡터 데이터베이스"""
    
    def __init__(self, similarity_threshold: float = 0.7, device: str = None):
        self.device = device or get_device()
        self.similarity_threshold = similarity_threshold
        print(f"🖥️  Device: {self.device}")
        
        # 벡터 저장소
        self.design_ids = []
        self.image_vectors = []
        self.text_vectors = []
        self.metadata = []
        
        # 모델
        self.clip_model = None
        self.clip_processor = None
        self.text_model = None
        self.text_device = None
    
    def load_models(self):
        """모델 로드"""
        print("📦 모델 로딩 중...")
        
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_model.to(self.device)
        self.clip_model.eval()
        print("✅ CLIP 모델 로드 완료")
        
        # MPS에서 sentence-transformers 호환성 이슈로 CPU 사용
        self.text_device = 'cpu' if self.device == 'mps' else self.device
        self.text_model = SentenceTransformer('jhgan/ko-sroberta-multitask')
        self.text_model.to(self.text_device)
        print(f"✅ 한국어 Sentence-BERT 로드 완료 (device: {self.text_device})")
    
    def extract_text_from_json(self, data: Dict) -> str:
        """JSON에서 텍스트 추출"""
        texts = []
        
        if data.get('meta', {}).get('articleName'):
            texts.append(data['meta']['articleName'])
        
        if data.get('creative', {}).get('designSummary'):
            summary = re.sub(r'<[^>]+>', '', data['creative']['designSummary'])
            texts.append(summary.strip())
        
        if data.get('creative', {}).get('designDescription'):
            desc = re.sub(r'<[^>]+>', '', data['creative']['designDescription'])
            texts.append(desc.strip())
        
        return ' '.join(texts)
    
    def get_image_from_url(self, url: str, timeout: int = 15) -> Optional[Image.Image]:
        """URL에서 이미지 다운로드"""
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert('RGB')
        except Exception as e:
            return None
    
    def encode_image(self, image: Image.Image) -> np.ndarray:
        """이미지 벡터화"""
        with torch.no_grad():
            inputs = self.clip_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            features = self.clip_model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
            return features.cpu().numpy().flatten()
    
    def encode_text(self, text: str) -> np.ndarray:
        """텍스트 벡터화"""
        embedding = self.text_model.encode(text, convert_to_numpy=True)
        return embedding / np.linalg.norm(embedding)
    
    def build_index(
        self,
        json_folder: str,
        save_path: str = "design_vectors.pkl"
    ):
        """전체 데이터 벡터화 및 인덱스 구축"""
        if self.clip_model is None:
            self.load_models()
        
        json_files = list(Path(json_folder).glob('*.json'))
        print(f"📁 총 {len(json_files)}개의 JSON 파일 발견")
        
        failed_images = []
        
        for json_path in tqdm(json_files, desc="벡터화 진행"):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                design_id = data.get('design_id', json_path.stem)
                
                # 텍스트 벡터화
                text = self.extract_text_from_json(data)
                text_vector = self.encode_text(text)
                
                # 이미지 벡터화
                image_vector = None
                image_url = data.get('image', {}).get('imagePath', '')
                
                if image_url:
                    image = self.get_image_from_url(image_url)
                    if image:
                        image_vector = self.encode_image(image)
                    else:
                        failed_images.append(design_id)
                    time.sleep(0.1)  # Rate limiting
                
                if image_vector is None:
                    image_vector = np.zeros(512)  # CLIP 벡터 크기
                
                # 저장
                self.design_ids.append(design_id)
                self.image_vectors.append(image_vector)
                self.text_vectors.append(text_vector)
                self.metadata.append({
                    'design_id': design_id,
                    'articleName': data.get('meta', {}).get('articleName', ''),
                    'LCCode': data.get('meta', {}).get('LCCode', ''),
                    'text': text,
                    'image_url': image_url,
                    'json_path': str(json_path)
                })
                
            except Exception as e:
                print(f"\n⚠️ 처리 실패 {json_path.name}: {e}")
        
        # numpy 배열로 변환
        self.image_vectors = np.array(self.image_vectors)
        self.text_vectors = np.array(self.text_vectors)
        
        # 저장
        self.save(save_path)
        
        print(f"\n✅ 벡터화 완료!")
        print(f"   총 디자인: {len(self.design_ids)}개")
        print(f"   이미지 실패: {len(failed_images)}개")
        print(f"   저장 위치: {save_path}")
        
        if failed_images:
            with open("failed_images.txt", 'w') as f:
                f.write('\n'.join(failed_images))
            print(f"   실패 목록: failed_images.txt")
    
    def save(self, path: str):
        """벡터 DB 저장"""
        data = {
            'design_ids': self.design_ids,
            'image_vectors': self.image_vectors,
            'text_vectors': self.text_vectors,
            'metadata': self.metadata
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        print(f"💾 저장 완료: {path}")
    
    def load(self, path: str):
        """벡터 DB 로드"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.design_ids = data['design_ids']
        self.image_vectors = data['image_vectors']
        self.text_vectors = data['text_vectors']
        self.metadata = data['metadata']
        print(f"📂 로드 완료: {len(self.design_ids)}개 디자인")
    
    def vector_to_string(self, vector: np.ndarray, precision: int = 6) -> str:
        """벡터를 문자열로 변환"""
        if vector is None or np.all(vector == 0):
            return ""
        return ','.join([f"{v:.{precision}f}" for v in vector])
    
    def compare_pair(
        self,
        idx1: int,
        idx2: int,
        image_weight: float = 0.7,
        text_weight: float = 0.3
    ) -> Dict:
        """두 디자인 비교"""
        img_sim = cosine_similarity(
            self.image_vectors[idx1].reshape(1, -1),
            self.image_vectors[idx2].reshape(1, -1)
        )[0][0]
        
        txt_sim = cosine_similarity(
            self.text_vectors[idx1].reshape(1, -1),
            self.text_vectors[idx2].reshape(1, -1)
        )[0][0]
        
        # 이미지 벡터가 0인 경우 (다운로드 실패) 텍스트만 사용
        if np.all(self.image_vectors[idx1] == 0) or np.all(self.image_vectors[idx2] == 0):
            total_sim = txt_sim
            img_sim = None
            # 이미지가 없으면 텍스트로 판정
            label = 1 if txt_sim >= self.similarity_threshold else 0
        else:
            total_sim = image_weight * img_sim + text_weight * txt_sim
            # image_similarity로 label 결정
            label = 1 if img_sim >= self.similarity_threshold else 0
        
        return {
            'idx1': idx1,
            'idx2': idx2,
            'design1_id': self.design_ids[idx1],
            'design2_id': self.design_ids[idx2],
            'design1_name': self.metadata[idx1]['articleName'],
            'design2_name': self.metadata[idx2]['articleName'],
            'design1_image_url': self.metadata[idx1]['image_url'],
            'design2_image_url': self.metadata[idx2]['image_url'],
            'design1_image_vector': self.image_vectors[idx1],
            'design2_image_vector': self.image_vectors[idx2],
            'design1_text_vector': self.text_vectors[idx1],
            'design2_text_vector': self.text_vectors[idx2],
            'image_similarity': float(img_sim) if img_sim is not None else None,
            'text_similarity': float(txt_sim),
            'total_similarity': float(total_sim),
            'label': label
        }
    
    def random_compare_and_save_csv(
        self,
        n_pairs: int = 100,
        output_csv: str = None,
        image_weight: float = 0.7,
        text_weight: float = 0.3,
        include_vectors: bool = True
    ) -> List[Dict]:
        """랜덤 쌍 비교 후 CSV 저장"""
        
        if len(self.design_ids) < 2:
            raise ValueError("최소 2개의 디자인이 필요합니다.")
        
        print(f"\n🎲 {n_pairs}개 쌍 랜덤 비교 시작...")
        print(f"📊 유사도 임계값: {self.similarity_threshold}")
        
        results = []
        
        for i in tqdm(range(n_pairs), desc="비교 진행"):
            idx1, idx2 = random.sample(range(len(self.design_ids)), 2)
            result = self.compare_pair(idx1, idx2, image_weight, text_weight)
            results.append(result)
        
        # CSV 저장
        if output_csv is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_csv = f"similarity_results_{timestamp}.csv"
        
        self._save_to_csv(results, output_csv, include_vectors)
        
        # 요약 통계
        labels = [r['label'] for r in results]
        valid_img_sims = [r['image_similarity'] for r in results if r['image_similarity'] is not None]
        
        print(f"\n{'='*60}")
        print(f"📈 요약 통계")
        print(f"  총 비교: {len(results)}쌍")
        print(f"  유사 (label=1): {sum(labels)}개 ({sum(labels)/len(labels)*100:.1f}%)")
        print(f"  비유사 (label=0): {len(labels)-sum(labels)}개")
        if valid_img_sims:
            print(f"  평균 이미지 유사도: {np.mean(valid_img_sims):.4f}")
        print(f"  평균 텍스트 유사도: {np.mean([r['text_similarity'] for r in results]):.4f}")
        print(f"  평균 종합 유사도: {np.mean([r['total_similarity'] for r in results]):.4f}")
        
        return results
    
    def _save_to_csv(
        self,
        results: List[Dict],
        output_path: str,
        include_vectors: bool = True
    ):
        """결과를 CSV 파일로 저장"""
        
        if include_vectors:
            headers = [
                'pair_id',
                'design1_id', 'design2_id',
                'design1_name', 'design2_name',
                'design1_image_url', 'design2_image_url',
                'image_similarity', 'text_similarity', 'total_similarity',
                'label',
                'design1_image_vector', 'design2_image_vector',
                'design1_text_vector', 'design2_text_vector'
            ]
        else:
            headers = [
                'pair_id',
                'design1_id', 'design2_id',
                'design1_name', 'design2_name',
                'design1_image_url', 'design2_image_url',
                'image_similarity', 'text_similarity', 'total_similarity',
                'label'
            ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            
            for i, r in enumerate(results):
                row = [
                    i + 1,
                    r['design1_id'],
                    r['design2_id'],
                    r['design1_name'],
                    r['design2_name'],
                    r['design1_image_url'],
                    r['design2_image_url'],
                    r['image_similarity'] if r['image_similarity'] is not None else '',
                    r['text_similarity'],
                    r['total_similarity'],
                    r['label']
                ]
                
                if include_vectors:
                    row.extend([
                        self.vector_to_string(r['design1_image_vector']),
                        self.vector_to_string(r['design2_image_vector']),
                        self.vector_to_string(r['design1_text_vector']),
                        self.vector_to_string(r['design2_text_vector'])
                    ])
                
                writer.writerow(row)
        
        print(f"\n💾 CSV 저장 완료: {output_path}")


def main():
    """메인 실행"""
    
    # ============================================================
    # 🔧 설정
    # ============================================================
    
    JSON_FOLDER = "./2000_json"  # JSON 파일 폴더
    VECTOR_DB_PATH = "09-01_2000_vectors.pkl"  # 벡터 DB 저장 경로
    OUTPUT_CSV = "09-01_2000_similarity_results.csv"  # 결과 CSV
    
    N_PAIRS = 2000  # 비교할 쌍 개수
    
    IMAGE_WEIGHT = 0.7  # 이미지 가중치
    TEXT_WEIGHT = 0.3  # 텍스트 가중치
    SIMILARITY_THRESHOLD = 0.5  # 유사 판정 임계값
    
    INCLUDE_VECTORS = False  # CSV에 벡터 포함 여부 (벡터 컬럼 제외)
    
    # ============================================================
    
    db = DesignVectorDB(similarity_threshold=SIMILARITY_THRESHOLD)
    
    # 벡터 DB 로드 또는 새로 생성
    if os.path.exists(VECTOR_DB_PATH):
        print("📂 기존 벡터 DB 로드 중...")
        db.load(VECTOR_DB_PATH)
    else:
        print("🔨 새 벡터 DB 구축 중... (시간이 걸릴 수 있습니다)")
        db.build_index(
            json_folder=JSON_FOLDER,
            save_path=VECTOR_DB_PATH
        )
    
    # 랜덤 비교 및 CSV 저장
    results = db.random_compare_and_save_csv(
        n_pairs=N_PAIRS,
        output_csv=OUTPUT_CSV,
        image_weight=IMAGE_WEIGHT,
        text_weight=TEXT_WEIGHT,
        include_vectors=INCLUDE_VECTORS
    )
    
    # 샘플 출력
    print(f"\n{'='*60}")
    print("📋 샘플 결과 (처음 3개)")
    print("="*60)
    
    for i, r in enumerate(results[:3]):
        label_emoji = "🔴 유사" if r['label'] == 1 else "🟢 비유사"
        print(f"\n#{i+1}")
        print(f"  Design 1: {r['design1_name']} ({r['design1_id']})")
        print(f"  Design 2: {r['design2_name']} ({r['design2_id']})")
        if r['image_similarity'] is not None:
            print(f"  이미지 유사도: {r['image_similarity']:.4f}")
        print(f"  텍스트 유사도: {r['text_similarity']:.4f}")
        print(f"  종합 유사도: {r['total_similarity']:.4f}")
        print(f"  라벨: {r['label']} {label_emoji}")
    
    print("\n✅ 완료!")


if __name__ == "__main__":
    main()