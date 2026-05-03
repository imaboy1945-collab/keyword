import os
import time
import hmac
import hashlib
import base64
import requests
import json

# 1. 환경 변수(Secrets) 설정
CUSTOMER_ID = os.environ.get('CUSTOMER_ID')
ACCESS_LICENSE = os.environ.get('ACCESS_LICENSE')
SECRET_KEY = os.environ.get('SECRET_KEY')
CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')

def generate_signature(timestamp, method, uri):
    message = "{}.{}.{}".format(timestamp, method, uri)
    hash = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash.digest()).decode('utf-8')

# 2. 네이버 검색광고 API: 연관 키워드 수집
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

# 3. 네이버 검색 API: 블로그 문서 수 조회
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

# 4. 등급 판정 로직
def calculate_grade(ratio):
    if ratio < 0.5: return "S"     # 황금 (검색량 대비 글 매우 적음)
    elif ratio < 2.0: return "A"   # 우수
    elif ratio < 5.0: return "B"   # 보통
    elif ratio < 10.0: return "C"  # 주의
    else: return "D"               # 과열 (경쟁 매우 높음)

# ==========================================
# 🎯 분석할 메인 키워드 설정 (최대 5개)
# ==========================================
SEED_KEYWORDS = ['주식', '환율', '미국', '이란'] 

try:
    combined_str = ','.join(SEED_KEYWORDS)
    print(f"'{combined_str}' 통합 분석 시작...")
    
    raw_data = get_related_keywords(combined_str)
    
    # 5. 검색량 데이터 정제 및 정렬
    cleaned_list = []
    for item in raw_data:
        pc = 10 if item['monthlyPcQcCnt'] == "< 10" else int(item['monthlyPcQcCnt'])
        mo = 10 if item['monthlyMobileQcCnt'] == "< 10" else int(item['monthlyMobileQcCnt'])
        total = pc + mo
        cleaned_list.append({
            'kw': item['relKeyword'],
            'pc': pc,
            'mo': mo,
            'total': total
        })
    
    # 총 검색량 기준 상위 50개 선정
    cleaned_list.sort(key=lambda x: x['total'], reverse=True)
    top_50 = cleaned_list[:50]
    
    # 6. 세부 분석 실행 (등급 및 문서 수)
    final_results = []
    for index, item in enumerate(top_50):
        kw_name = item['kw']
        blog_cnt = get_blog_count(kw_name)
        total_s = item['total']
        
        # 경쟁률 계산 및 등급 판정
        ratio = round(blog_cnt / total_s, 2) if total_s > 0 else 0
        grade = calculate_grade(ratio)
        
        final_results.append({
            "no": index + 1,
            "keyword": kw_name,
            "pc_search": item['pc'],
            "mobile_search": item['mo'],
            "daily_avg": round(total_s / 30, 2),
            "grade": grade,
            "ratio": ratio,
            "blog_total": blog_cnt
        })
        print(f"[{index+1}/50] {kw_name} 분석 완료")
        time.sleep(0.1) # API 보호
        
    # 결과 저장
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)
    print("분석 데이터 업데이트 성공!")

except Exception as e:
    print(f"오류가 발생했습니다: {e}")
