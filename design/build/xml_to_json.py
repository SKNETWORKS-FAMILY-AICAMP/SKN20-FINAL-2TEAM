import xml.etree.ElementTree as ET
import json
import os
from pathlib import Path


def extract_text(element, default=""):
    """XML 요소에서 텍스트 추출"""
    if element is not None and element.text:
        return element.text.strip()
    return default


def parse_xml_to_json_per_image(xml_file_path, locarno_code):
    """
    XML 파일을 이미지 당 하나의 JSON으로 변환
    
    Args:
        xml_file_path: XML 파일 경로
        locarno_code: 로카르노 분류 코드 (예: "09-99")
    
    Returns:
        JSON 형식의 딕셔너리 리스트 (이미지 개수만큼)
    """
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    # XML 네임스페이스 제거 (필요시)
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
    
    # 기본 정보 추출
    biblio_info = root.find('.//biblioSummaryInfo')
    if biblio_info is None:
        return []
    
    application_number = extract_text(biblio_info.find('applicationNumber'))
    design_number = extract_text(biblio_info.find('designNumber'))
    reg_fg = extract_text(biblio_info.find('regFg'))
    admst_stat = extract_text(biblio_info.find('admstStat'))
    last_disposition_date = extract_text(biblio_info.find('lastDispositionDate'))
    article_name = extract_text(biblio_info.find('articleName'))
    registration_number = extract_text(biblio_info.find('registrationNumber'))
    publication_number = extract_text(biblio_info.find('publicationNumber'))
    
    # 출원인명 추출
    applicant_name = ""
    applicant_info = root.find('.//applicantInfo')
    if applicant_info is not None:
        applicant_name = extract_text(applicant_info.find('applicantName'))
    
    # 대리인명 추출
    agent_name = ""
    agent_info = root.find('.//agentInfo')
    if agent_info is not None:
        agent_name = extract_text(agent_info.find('agentName'))
    
    # 창작의 요점, 내용 추출
    design_summary = ""
    creative_summary_info = root.find('.//creativeSummaryInfo')
    if creative_summary_info is not None:
        design_summary = extract_text(creative_summary_info.find('designSummary'))
        # HTML 엔티티 디코딩
        design_summary = design_summary.replace('&quot;', '"')
    
    design_description = ""
    creative_description_info = root.find('.//creativeDescriptionInfo')
    if creative_description_info is not None:
        design_description = extract_text(creative_description_info.find('designDescription'))
    
    # 도면 이미지 정보 추출 (도면 번호 0, 1, 2만 추출)
    image_data = []
    design_image_info = root.find('.//designImageInfo')
    if design_image_info is not None:
        image_paths = design_image_info.findall('imagePath')
        for image_path in image_paths:
            image_name = extract_text(image_path.find('imageName'))
            large_path = extract_text(image_path.find('largePath'))
            number = extract_text(image_path.find('number'))
            
            # 도면 번호가 0, 1, 2인 것만 추출
            try:
                num_int = int(number)
                if num_int not in [0, 1, 2]:  # 0, 1, 2만 수집
                    continue
            except:
                continue
            
            image_data.append({
                'number': number,
                'imageName': image_name,
                'imagePath': large_path
            })
    
    # 날짜 형식 변환 (YYYY.MM.DD -> YYYY-MM-DD)
    if last_disposition_date and len(last_disposition_date) == 10:
        last_disposition_date = last_disposition_date.replace('.', '-')
    
    # 이미지 개수만큼 JSON 생성
    json_list = []
    for img in image_data:
        design_id = f"{application_number}-{locarno_code}-{img['number']}"
        
        json_data = {
            "design_id": design_id,
            "applicationNumber": application_number,
            "registrationNumber": registration_number,
            "publicationNumber": publication_number,
            "status": {
                "regFg": reg_fg,
                "admstStat": admst_stat,
                "lastDispositionDate": last_disposition_date
            },
            "meta": {
                "articleName": article_name,
                "LCCode": locarno_code,
                "designNumber": design_number,
                "applicantName": applicant_name,
                "agentName": agent_name
            },
            "image": {
                "image_id": f"{application_number}-{img['number']}",
                "imageName": img['imageName'],
                "imagePath": img['imagePath'],
                "number": img['number']
            },
            "creative": {
                "designSummary": design_summary,
                "designDescription": design_description
            }
        }
        
        json_list.append(json_data)
    
    return json_list


def convert_folder_per_image(source_folder_path, output_folder_path, locarno_code):
    """
    폴더 내의 모든 XML 파일을 이미지당 JSON으로 변환
    
    Args:
        source_folder_path: XML 파일들이 있는 폴더 경로
        output_folder_path: JSON 파일 저장 폴더 경로
        locarno_code: 로카르노 분류 코드
    """
    xml_files = list(Path(source_folder_path).glob("*.xml"))
    
    # 출력 폴더 생성
    output_dir = Path(output_folder_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    total_json_count = 0
    
    for xml_file in sorted(xml_files):
        try:
            print(f"변환 중: {xml_file.name}")
            json_list = parse_xml_to_json_per_image(str(xml_file), locarno_code)
            
            if json_list:
                for json_data in json_list:
                    # JSON 파일명: {출원번호}-{도면번호}.json
                    image_number = json_data['image']['number']
                    json_file_name = f"{json_data['applicationNumber']}-{image_number}.json"
                    json_file_path = output_dir / json_file_name
                    
                    with open(json_file_path, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    
                    total_json_count += 1
                
                results.append({
                    'xml_file': xml_file.name,
                    'json_count': len(json_list),
                    'status': 'success'
                })
                print(f"  ✓ {len(json_list)}개 JSON 파일 생성 완료")
            else:
                results.append({
                    'xml_file': xml_file.name,
                    'status': 'error',
                    'message': 'biblioSummaryInfo를 찾을 수 없음'
                })
                print(f"  ✗ 변환 실패: {xml_file.name}")
                
        except Exception as e:
            results.append({
                'xml_file': xml_file.name,
                'status': 'error',
                'message': str(e)
            })
            print(f"  ✗ 오류: {xml_file.name} - {str(e)}")
    
    return results, total_json_count


if __name__ == "__main__":
    # 현재 디렉토리 경로
    current_dir = Path(__file__).parent
    
    # xml\2025_2026 폴더 변환
    input_folder = current_dir / "../data/xml/2025_2026" #변경할 xml 폴더 경로
    output_folder = current_dir / "../data/json/2025_2026" #변경된 json 폴더 경로
    if input_folder.exists():
        print("=" * 50)
        print(f"{input_folder} 폴더 변환 시작 (이미지당 JSON 1개)")
        print("=" * 50)
        results, count = convert_folder_per_image(str(input_folder), str(output_folder), "09-01")
        success_count = len([r for r in results if r['status'] == 'success'])
        print(f"\n09-99: {success_count}/{len(results)} XML 변환 완료 → {count}개 JSON 파일 생성\n")
    
    print("=" * 50)
    print("변환 완료!")
    print("=" * 50)
