import os
import xml.etree.ElementTree as ET
import csv
from pathlib import Path
import requests
from urllib.parse import urlparse
import time

def extract_images_from_xml(xml_file_path):
    """
    XML 파일에서 이미지 정보를 추출합니다.
    
    Args:
        xml_file_path: XML 파일 경로
        
    Returns:
        List of dict containing image information
    """
    images = []
    
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        # designImageInfoArray 찾기
        for design_image_info in root.findall('.//designImageInfo'):
            application_number = design_image_info.findtext('applicationNumber', 'N/A')
            design_number = design_image_info.findtext('designNumber', 'N/A')
            
            # imagePath 요소들 찾기
            for idx, image_path in enumerate(design_image_info.findall('imagePath')):
                image_name = image_path.findtext('imageName', 'N/A')
                large_path = image_path.findtext('largePath', 'N/A')
                small_path = image_path.findtext('smallPath', 'N/A')
                number = image_path.findtext('number', 'N/A')
                
                images.append({
                    'application_number': application_number,
                    'design_number': design_number,
                    'image_name': image_name,
                    'image_number': number,
                    'large_url': large_path,
                    'small_url': small_path
                })
    
    except ET.ParseError as e:
        print(f"❌ XML 파싱 오류 ({xml_file_path}): {e}")
    except Exception as e:
        print(f"❌ 오류 ({xml_file_path}): {e}")
    
    return images

def download_image(url, file_path, timeout=20):
    """
    URL에서 이미지를 다운로드하여 파일로 저장합니다.
    
    Args:
        url: 이미지 URL
        file_path: 저장할 파일 경로
        timeout: 요청 타임아웃 (초)
        
    Returns:
        성공 여부 (True/False)
    """
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(response.content)
            return True
        else:
            return False
    except Exception as e:
        print(f"❌ 다운로드 오류 ({url}): {e}")
        return False

def main():
    xml_folder = "28-03"
    output_img_folder = "28-03_img"
    output_csv = "28-03_images_extraction.csv"
    
    if not os.path.exists(xml_folder):
        print(f"❌ 폴더를 찾을 수 없습니다: {xml_folder}")
        return
    
    # 이미지 저장 폴더 생성
    os.makedirs(output_img_folder, exist_ok=True)
    
    # 모든 XML 파일 찾기
    xml_files = sorted([f for f in Path(xml_folder).glob("*.xml")])
    
    if not xml_files:
        print(f"❌ {xml_folder} 폴더에 XML 파일이 없습니다.")
        return
    
    print(f"📂 {xml_folder} 폴더에서 {len(xml_files)}개의 XML 파일을 발견했습니다.\n")
    
    all_images = []
    total_images = 0
    downloaded_count = 0
    failed_count = 0
    
    # 각 XML 파일 처리
    for xml_idx, xml_file in enumerate(xml_files, 1):
        images = extract_images_from_xml(str(xml_file))
        total_images += len(images)
        
        if images:
            print(f"[{xml_idx}/{len(xml_files)}] {xml_file.name}: {len(images)}개 이미지 추출")
            
            # 각 이미지 다운로드
            for img_info in images:
                app_num = img_info['application_number']
                design_num = img_info['design_number']
                img_num = img_info['image_number']
                large_url = img_info['large_url']
                
                # 폴더 구조: 28-03_img/출원번호/디자인번호_이미지번호.jpeg
                img_folder = os.path.join(output_img_folder, app_num)
                os.makedirs(img_folder, exist_ok=True)
                
                img_file_name = f"{design_num}_{img_num}.jpeg"
                img_file_path = os.path.join(img_folder, img_file_name)
                
                # 이미지 다운로드
                if large_url and large_url != 'N/A':
                    if download_image(large_url, img_file_path):
                        downloaded_count += 1
                        print(f"    ✅ {img_file_name}")
                    else:
                        failed_count += 1
                        print(f"    ⚠️  {img_file_name} (다운로드 실패)")
                    
                    time.sleep(0.2)  # API 요청 간 딜레이
                
                all_images.append(img_info)
        else:
            print(f"[{xml_idx}/{len(xml_files)}] {xml_file.name}: 이미지 없음")
    
    # CSV 파일로 저장
    if all_images:
        keys = all_images[0].keys()
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_images)
        
        print(f"\n{'='*60}")
        print(f"✅ 완료!")
        print(f"   📊 총 {total_images}개의 이미지 정보 추출")
        print(f"   🖼️  {downloaded_count}개의 이미지 다운로드 성공")
        print(f"   ⚠️  {failed_count}개의 이미지 다운로드 실패")
        print(f"   📁 이미지 저장 경로: {output_img_folder}")
        print(f"   📄 메타데이터 저장: {output_csv}")
        print(f"{'='*60}")
    else:
        print(f"\n⚠️  추출된 이미지가 없습니다.")

if __name__ == "__main__":
    main()
