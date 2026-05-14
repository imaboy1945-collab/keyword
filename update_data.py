import os
import time
import hmac
import hashlib
import base64
import requests
import json

# 1. GitHub Actions에서 설정한 환경변수를 그대로 가져옵니다.
CUSTOMER_ID = os.environ.get('NAVER_CUSTOMER_ID')
ACCESS_LICENSE = os.environ.get('NAVER_ACCESS_LICENSE')
SECRET_KEY = os.environ.get('NAVER_SECRET_KEY')
CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')

def generate_signature(timestamp, method, uri):
    message = "{}.{}.{}".format(timestamp, method, uri)
    hash = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash.digest()).decode('utf-8')

# 네이버 검색광고 API (연관 키워드 추출)
def get_related_keywords(keywords_str):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(int(time.time() * 1000))
    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': ACCESS_LICENSE,
        'X-Customer': CUSTOMER_ID,
        'X-Signature': generate_signature(timestamp, method, uri)
    }
    params = {'hintKeywords': keywords_str, 'showDetail': '1'}
    res = requests.get('https://api.naver.com' + uri, params=params, headers=headers)
    return res.json()['keywordList']

# 네이버 검색 API (블로그 문서 수 추출) - 401 에러 해결 포인트
def get_blog_count(keyword):
    url = f"https://openapi.naver.com/v1/search/blog.json?query={keyword}&display=1"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get('total', 0)
    else:
        # 에러 로그 출력 (Actions 탭에서 확인 가능)
        print(f"Search API Error: {res.status_code} | ID: {CLIENT_ID[:5]}... | Keyword: {keyword}")
        return 0

def calculate_grade(ratio):
    if ratio < 0.5: return "S"
    elif ratio < 2.0: return "A"
    elif ratio < 5.0: return "B"
    elif ratio < 10.0: return "C"
    else: return "D"

# ==========================================
# 🎯 분석할 메인 키워드 설정
# ==========================================
SEED_KEYWORDS = ['주식정보', '생활꿀팀', '복지정책', '추천여행', '건강정보'] 

try:
    combined_str = ','.join(SEED_KEYWORDS)
    print(f"'{combined_str}' 통합 분석 시작...")
    
    raw_data = get_related_keywords(combined_str)
    
    cleaned_list = []
    for item in raw_data:
        pc = 10 if item['monthlyPcQcCnt'] == "< 10" else int(item['monthlyPcQcCnt'])
        mo = 10 if item['monthlyMobileQcCnt'] == "< 10" else int(item['monthlyMobileQcCnt'])
        total = pc + mo
        cleaned_list.append({'kw': item['relKeyword'], 'pc': pc, 'mo': mo, 'total': total})
    
    cleaned_list.sort(key=lambda x: x['total'], reverse=True)
    top_50 = cleaned_list[:50]
    
    final_results = []
    for index, item in enumerate(top_50):
        kw_name = item['kw']
        blog_cnt = get_blog_count(kw_name)
        total_s = item['total']
        ratio = round(blog_cnt / total_s, 2) if total_s > 0 else 0
        
        final_results.append({
            "no": index + 1,
            "keyword": kw_name,
            "pc_search": item['pc'],
            "mobile_search": item['mo'],
            "daily_avg": round(total_s / 30, 2),
            "grade": calculate_grade(ratio),
            "ratio": ratio,
            "blog_total": blog_cnt
        })
        time.sleep(0.1) # 과부하 방지
        
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)
    print("성공적으로 데이터를 업데이트했습니다.")

except Exception as e:
    print(f"오류 발생: {e}")
