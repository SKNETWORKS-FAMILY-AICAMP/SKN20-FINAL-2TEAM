import requests
from bs4 import BeautifulSoup
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

def crawl_vogue_article(url):
    """
    보그 한국 사이트에서 제목, 본문, 날짜를 크롤링합니다.
    
    Args:
        url (str): 크롤링할 기사 URL
        
    Returns:
        dict: 제목, 본문, 날짜를 포함한 딕셔너리
    """
    try:
        # 요청 헤더 설정
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # 웹페이지 요청
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {"error": f"HTTP Error: {response.status_code}"}
        
        # BeautifulSoup으로 파싱
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 제목 추출
        title = None
        title_tag = soup.find('h1')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # 날짜 추출
        date = None
        # 메타 데이터에서 날짜 찾기
        date_meta = soup.find('meta', property='article:published_time')
        if date_meta:
            date = date_meta.get('content', '').split('T')[0]
        
        # 메타 데이터 실패시 다른 방식 시도
        if not date:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    import json
                    data = json.loads(script.string)
                    if 'datePublished' in data:
                        date = data['datePublished'].split('T')[0]
                        break
                except:
                    pass
        
        # 마지막 시도: 텍스트에서 패턴 찾기
        if not date:
            date_patterns = soup.find_all(string=lambda text: text and len(text.strip()) > 0)
            for text in date_patterns:
                text_clean = text.strip()
                if text_clean and (text_clean.startswith('2026.') or text_clean.startswith('2025.')):
                    date = text_clean
                    break
        
        # 본문 추출
        content = ""
        article_body = soup.find('article')
        if not article_body:
            article_body = soup.find('div', class_=lambda x: x and 'article' in x.lower())
        if not article_body:
            article_body = soup.find('div', class_=lambda x: x and 'content' in x.lower())
        
        if article_body:
            paragraphs = article_body.find_all('p')
            content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
        
        # 결과 반환
        result = {
            "title": title,
            "date": date,
            "content": content,
            "url": url
        }
        
        return result
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"error": f"Parsing error: {str(e)}"}


def save_to_json(data, filename="vogue_article.json"):
    """
    크롤링한 데이터를 JSON 파일로 저장합니다.
    
    Args:
        data (dict): 저장할 데이터
        filename (str): 저장할 파일명
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ 데이터가 {filename}에 저장되었습니다.")


def crawl_multiple_urls(urls, max_workers=5):
    """
    여러 URL을 동시에 크롤링합니다.
    
    Args:
        urls (list): 크롤링할 URL 리스트
        max_workers (int): 동시에 실행할 최대 스레드 수
        
    Returns:
        list: 크롤링 결과 리스트
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 모든 URL에 대해 크롤링 작업 제출
        future_to_url = {executor.submit(crawl_vogue_article, url): url for url in urls}
        
        # 완료된 작업부터 처리
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
                print(f"✓ 완료: {url}")
            except Exception as e:
                print(f"❌ 오류 ({url}): {str(e)}")
                results.append({"error": f"Request error: {str(e)}", "url": url})
    
    return results


if __name__ == "__main__":
    # 크롤링할 URL 리스트 (여기에 원하는 URL을 추가하세요)
    urls = [
        "https://www.vogue.co.kr/?p=746528",
        "https://www.vogue.co.kr/?p=742818",
        "https://www.vogue.co.kr/?p=735902",
        "https://www.vogue.co.kr/?p=712849",
        "https://www.vogue.co.kr/?p=713047",
        "https://www.vogue.co.kr/?p=706860",
        "https://www.vogue.co.kr/?p=699207",
        "https://www.vogue.co.kr/?p=691391",
        "https://www.vogue.co.kr/?p=679131", #0122 18:42 

    ]
    
    print(f"🚀 {len(urls)}개 URL 동시 크롤링 시작...")
    print("-" * 50)
    
    # 여러 URL 동시 크롤링
    results = crawl_multiple_urls(urls, max_workers=5)
    
    print("-" * 50)
    print(f"✓ 총 {len(results)}개 기사 크롤링 완료")
    
    # 결과를 JSON으로 저장
    save_to_json(results, "vogue_articles.json")
    
    # 터미널에 결과 요약 출력
    print("\n" + "="*50)
    print("크롤링 결과 요약:")
    for i, article in enumerate(results, 1):
        if "error" not in article:
            print(f"\n[{i}] {article['title']}")
            print(f"    날짜: {article['date']}")
            print(f"    URL: {article['url']}")
        else:
            print(f"\n[{i}] ❌ 오류: {article['url']}")
            print(f"    {article['error']}")
