import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


CUSTOMER_ID = os.environ.get("NAVER_CUSTOMER_ID")
ACCESS_LICENSE = os.environ.get("NAVER_ACCESS_LICENSE")
SECRET_KEY = os.environ.get("NAVER_SECRET_KEY")
CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

DEFAULT_SEED_KEYWORDS = ["주식정보", "생활꿀팁", "복지정책", "추천여행", "건강정보"]
SEED_KEYWORDS = [
    keyword.strip()
    for keyword in os.environ.get("SEED_KEYWORDS", ",".join(DEFAULT_SEED_KEYWORDS)).split(",")
    if keyword.strip()
]
EXCLUDE_PATTERNS = [
    pattern.strip()
    for pattern in os.environ.get("EXCLUDE_PATTERNS", "").split(",")
    if pattern.strip()
]

OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "data.json")
MAX_KEYWORDS = int(os.environ.get("MAX_KEYWORDS", "120"))
MIN_MONTHLY_SEARCH = int(os.environ.get("MIN_MONTHLY_SEARCH", "50"))
NAVER_DELAY_SECONDS = float(os.environ.get("NAVER_DELAY_SECONDS", "0.15"))
KST = timezone(timedelta(hours=9))


class ScannerError(RuntimeError):
    pass


def make_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "bestwellth-keyword-scanner/2.0"})
    return session


SESSION = make_session()


def require_env() -> None:
    required = {
        "NAVER_CUSTOMER_ID": CUSTOMER_ID,
        "NAVER_ACCESS_LICENSE": ACCESS_LICENSE,
        "NAVER_SECRET_KEY": SECRET_KEY,
        "NAVER_CLIENT_ID": CLIENT_ID,
        "NAVER_CLIENT_SECRET": CLIENT_SECRET,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ScannerError(f"GitHub Secrets 환경변수가 빠졌습니다: {', '.join(missing)}")


def generate_signature(timestamp: str, method: str, uri: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def parse_count(value: Any) -> int:
    if value in (None, "", "-"):
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "")
    if text == "< 10":
        return 10
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword.strip())


def is_excluded(keyword: str) -> bool:
    return any(re.search(pattern, keyword, re.IGNORECASE) for pattern in EXCLUDE_PATTERNS)


def get_related_keywords(seed_keyword: str) -> list[dict[str, Any]]:
    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": ACCESS_LICENSE,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": generate_signature(timestamp, method, uri),
    }
    params = {"hintKeywords": seed_keyword, "showDetail": "1"}
    response = SESSION.get("https://api.naver.com" + uri, params=params, headers=headers, timeout=20)
    if response.status_code != 200:
        raise ScannerError(f"검색광고 API 오류: {response.status_code} | seed={seed_keyword} | {response.text[:300]}")
    return response.json().get("keywordList", [])


def get_search_total(keyword: str, target: str) -> int:
    encoded = quote(keyword)
    url = f"https://openapi.naver.com/v1/search/{target}.json?query={encoded}&display=1"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }
    response = SESSION.get(url, headers=headers, timeout=20)
    if response.status_code != 200:
        print(f"Search API Error: {response.status_code} | target={target} | keyword={keyword} | {response.text[:180]}")
        return 0
    return int(response.json().get("total", 0))


def calculate_grade(ratio: float, daily_avg: float, mobile_share: float) -> str:
    if ratio < 0.5 and daily_avg >= 20 and mobile_share >= 0.45:
        return "S"
    if ratio < 1.5 and daily_avg >= 10:
        return "A"
    if ratio < 4.0:
        return "B"
    if ratio < 8.0:
        return "C"
    return "D"


def opportunity_score(monthly_total: int, blog_total: int, cafe_total: int, news_total: int) -> float:
    demand = monthly_total / 30
    competition = max(blog_total + (cafe_total * 0.35) + (news_total * 0.2), 1)
    return round((demand * 1000) / competition, 3)


def collect_candidates() -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for seed in SEED_KEYWORDS:
        print(f"[related] '{seed}' 연관 키워드 수집 중...")
        for item in get_related_keywords(seed):
            keyword = normalize_keyword(item.get("relKeyword", ""))
            if not keyword or is_excluded(keyword):
                continue

            pc = parse_count(item.get("monthlyPcQcCnt"))
            mobile = parse_count(item.get("monthlyMobileQcCnt"))
            monthly_total = pc + mobile
            if monthly_total < MIN_MONTHLY_SEARCH:
                continue

            existing = candidates.get(keyword)
            if not existing or monthly_total > existing["monthly_total"]:
                candidates[keyword] = {
                    "keyword": keyword,
                    "seed": seed,
                    "pc_search": pc,
                    "mobile_search": mobile,
                    "monthly_total": monthly_total,
                }
        time.sleep(NAVER_DELAY_SECONDS)
    return candidates


def analyze_keywords(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    limit = min(len(candidates), MAX_KEYWORDS)
    for index, item in enumerate(candidates[:MAX_KEYWORDS], start=1):
        keyword = item["keyword"]
        print(f"[analyze] {index}/{limit} {keyword}")

        blog_total = get_search_total(keyword, "blog")
        time.sleep(NAVER_DELAY_SECONDS)
        cafe_total = get_search_total(keyword, "cafearticle")
        time.sleep(NAVER_DELAY_SECONDS)
        news_total = get_search_total(keyword, "news")
        time.sleep(NAVER_DELAY_SECONDS)

        monthly_total = item["monthly_total"]
        daily_avg = round(monthly_total / 30, 2)
        ratio = round(blog_total / monthly_total, 2) if monthly_total > 0 else 0
        mobile_share = round(item["mobile_search"] / monthly_total, 3) if monthly_total > 0 else 0
        score = opportunity_score(monthly_total, blog_total, cafe_total, news_total)

        results.append(
            {
                "no": index,
                "keyword": keyword,
                "seed": item["seed"],
                "pc_search": item["pc_search"],
                "mobile_search": item["mobile_search"],
                "monthly_total": monthly_total,
                "daily_avg": daily_avg,
                "mobile_share": mobile_share,
                "grade": calculate_grade(ratio, daily_avg, mobile_share),
                "opportunity_score": score,
                "ratio": ratio,
                "blog_total": blog_total,
                "cafe_total": cafe_total,
                "news_total": news_total,
            }
        )

    grade_rank = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    results.sort(key=lambda row: (grade_rank.get(row["grade"], 9), -row["opportunity_score"], -row["monthly_total"]))
    for index, row in enumerate(results, start=1):
        row["no"] = index
    return results


def main() -> int:
    require_env()
    started_at = datetime.now(KST).isoformat(timespec="seconds")
    print(f"키워드 자동 분석 시작: {started_at}")
    print(f"시드 키워드: {', '.join(SEED_KEYWORDS)}")

    candidates = list(collect_candidates().values())
    candidates.sort(key=lambda row: row["monthly_total"], reverse=True)
    print(f"분석 후보: {len(candidates)}개 / 실제 분석: {min(len(candidates), MAX_KEYWORDS)}개")

    results = analyze_keywords(candidates)
    updated_at = datetime.now(KST).isoformat(timespec="seconds")
    for row in results:
        row["updated_at"] = updated_at

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    print(f"성공: {OUTPUT_FILE}에 {len(results)}개 키워드를 저장했습니다.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"오류 발생: {exc}", file=sys.stderr)
        raise SystemExit(1)
