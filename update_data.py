import os
import time
import hmac
import hashlib
import base64
import requests
import json

# 1. 환경 변수(Secrets)에서 API 키 불러오기
CUSTOMER_ID = os.environ.get('CUSTOMER_ID')
ACCESS_LICENSE = os.environ.get('ACCESS_LICENSE')
SECRET_KEY = os.environ.get('SECRET_KEY')
CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')

def generate_signature(timestamp, method, uri):
    message = "{}.{}.{}".format(timestamp, method, uri)
    hash = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash.digest()).decode('utf-8')

# 2. 네이버 검색광고 API: 연관 키워드 및 검색량 수집
def get_related_keywords(seed_keyword):
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
    params = {'hintKeywords': seed_keyword, 'showDetail': '1'}
    res = requests.get('https://api.naver.com' + uri, params=params, headers=headers)
    return res.json()['keywordList']

# 3. 네이버 검색 API: 블로그 전체 문서 수 수집
def get_blog_count(keyword):
    url = f"https://openapi.naver.com/v1/search/blog.json?query={keyword}&display=1"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get('total', 0)
    return 0

# 4. 키워드 등급 계산 로직
def calculate_grade(ratio):
    if ratio < 0.5: return "S"     # 황금 키워드
    elif ratio < 2.0: return "A"   # 우수
    elif ratio < 5.0: return "B"   # 보통
    elif ratio < 10.0: return "C"  # 주의
    else: return "D"               # 과열

# ==========================================
# 🎯 분석할 메인 키워드 설정 (여기만 수정하세요)
# ==========================================
SEED_KEYWORD = '워드프레스' 

try:
    print(f"'{SEED_KEYWORD}' 관련 키워드 분석 중...")
    raw_data = get_related_keywords(SEED_KEYWORD)
    
    # 검색량 기준 정렬 및 상위 50개 추출
    cleaned_data = []
    for item in raw_data:
        pc = 10 if item['monthlyPcQcCnt'] == "< 10" else int(item['monthlyPcQcCnt'])
        mo = 10 if item['monthlyMobileQcCnt'] == "< 10" else int(item['monthlyMobileQcCnt'])
        item['total_search'] = pc + mo
        item['pc_cnt'] = pc
        item['mo_cnt'] = mo
        cleaned_data.append(item)
    
    cleaned_data.sort(key=lambda x: x['total_search'], reverse=True)
    top_50 = cleaned_data[:50]
    
    processed_result = []
    for index, item in enumerate(top_50):
        kw = item['relKeyword']
        blog_total = get_blog_count(kw)
        total_s = item['total_search']
        
        # 경쟁률(비율) 및 등급 판정
        ratio = round(blog_total / total_s, 2) if total_s > 0 else 0
        grade = calculate_grade(ratio)
        
        processed_result.append({
            "no": index + 1,
            "keyword": kw,
            "pc_search": item['pc_cnt'],
            "mobile_search": item['mo_cnt'],
            "daily_avg": round(total_s / 30, 2),
            "grade": grade,
            "blog_total": blog_total,
            "ratio": ratio
        })
        time.sleep(0.1) # API 속도 제한 준수
        
    # 결과 저장
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_result, f, ensure_ascii=False, indent=4)
    print("완료! data.json 파일이 업데이트되었습니다.")

except Exception as e:
    print(f"오류 발생: {e}")
