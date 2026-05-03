import os
import time
import hmac
import hashlib
import base64
import requests
import json

# API 키 설정
CUSTOMER_ID = os.environ.get('CUSTOMER_ID')
ACCESS_LICENSE = os.environ.get('ACCESS_LICENSE')
SECRET_KEY = os.environ.get('SECRET_KEY')
CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')

def generate_signature(timestamp, method, uri):
    message = "{}.{}.{}".format(timestamp, method, uri)
    hash = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash.digest()).decode('utf-8')

# 1. 메인 키워드로 연관 검색어 무더기 가져오기
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

# 2. 블로그 문서 수 가져오기
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

def calculate_grade(ratio):
    if ratio < 0.5: return "S"
    elif ratio < 2.0: return "A"
    elif ratio < 5.0: return "B"
    elif ratio < 10.0: return "C"
    else: return "D"

# ==========================================
# 🎯 여기서 검색하고 싶은 "핵심 단어 1개"만 입력하세요!
# ==========================================
SEED_KEYWORD = '워드프레스'

try:
    print(f"'{SEED_KEYWORD}' 연관 키워드 수집 시작...")
    raw_data = get_related_keywords(SEED_KEYWORD)
    
    # 데이터 정제 및 총 검색량 계산
    cleaned_data = []
    for item in raw_data:
        pc_cnt = 10 if item['monthlyPcQcCnt'] == "< 10" else int(item['monthlyPcQcCnt'])
        mobile_cnt = 10 if item['monthlyMobileQcCnt'] == "< 10" else int(item['monthlyMobileQcCnt'])
        total_search = pc_cnt + mobile_cnt
        item['total_search'] = total_search
        item['pc_cnt'] = pc_cnt
        item['mobile_cnt'] = mobile_cnt
        cleaned_data.append(item)
    
    # 검색량 기준 내림차순 정렬 후 상위 50개만 컷! (API 보호 및 속도 향상)
    cleaned_data.sort(key=lambda x: x['total_search'], reverse=True)
    top_50_keywords = cleaned_data[:50]
    
    processed_data = []
    
    for index, item in enumerate(top_50_keywords):
        keyword = item['relKeyword']
        pc_cnt = item['pc_cnt']
        mobile_cnt = item['mobile_cnt']
        total_search = item['total_search']
        
        # 블로그 문서 수 조회
        blog_total = get_blog_count(keyword)
        
        # 경쟁률 및 등급 계산
        ratio = round(blog_total / total_search, 2) if total_search > 0 else 0
        grade = calculate_grade(ratio)
        
        processed_data.append({
            "no": index + 1,
            "keyword": keyword,
            "pc_search": pc_cnt,
            "mobile_search": mobile_cnt,
            "daily_avg": round(total_search / 30, 2),
            "grade": grade,
            "blog_total": blog_total,
            "ratio": ratio
        })
        print(f"[{index+1}/50] {keyword} 분석 완료")
        time.sleep(0.1) # 네이버 서버가 공격으로 오해하지 않게 살짝 쉬어줌
        
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)
    print("성공적으로 데이터가 업데이트되었습니다!")

except Exception as e:
    print(f"Error: {e}")
