"""
서울우유 홈페이지 크롤러 (이미지 URL 추출 추가)
- 실행: python crawling/crawler.py
"""

import json
import time
import ssl
import urllib3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://m.seoulmilk.co.kr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


session = requests.Session()
session.mount("https://", SSLAdapter())


def get_soup(url: str) -> BeautifulSoup | None:
    try:
        res = session.get(url, headers=HEADERS, timeout=15, verify=False)
        res.raise_for_status()
        res.encoding = "utf-8"
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"  [오류] {url} → {e}")
        return None


def save_json(data: list | dict, filename: str):
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  저장 완료: {path} ({len(data)}건)")


# ────────────────────────────────────────────
# 1. 제품 정보 크롤링
# ────────────────────────────────────────────
PRODUCT_CATEGORIES = {
    "P0": "우유",
    "P1": "발효유",
    "P2": "음료",
    "P3": "커피",
    "P4": "치즈",
    "P5": "크림·버터",
    "P6": "분유·연유",
    "P7": "디저트·아이스크림",
}


def crawl_products() -> list[dict]:
    print("\n[1/3] 제품 정보 크롤링 시작...")
    products = []

    for cat_code, cat_name in PRODUCT_CATEGORIES.items():
        list_url = f"{BASE_URL}/mobile/product/product_list.sm?subname={cat_code}&page=1"
        print(f"  카테고리: {cat_name} ({cat_code})")
        soup = get_soup(list_url)
        if not soup:
            continue

        links = soup.find_all("a", href=lambda h: h and "product_view" in str(h))
        print(f"    제품 링크 {len(links)}개 발견")

        for link in links[:15]:
            href = link.get("href", "")
            if not href:
                continue

            # nmNo 파라미터 추출
            nm_no = ""
            for part in href.split("&"):
                if "nmNo=" in part:
                    nm_no = part.split("=")[-1]
                    break
            if not nm_no:
                continue

            detail_url = (
                f"{BASE_URL}/mobile/product/product_view.sm"
                f"?subname={cat_code}&gubun=&nmNo={nm_no}&page=1"
            )

            detail = crawl_product_detail(detail_url, cat_name)
            if detail:
                products.append(detail)
                print(f"    ✓ {detail['name']}")
            else:
                print(f"    ✗ 파싱 실패: {detail_url}")
            time.sleep(0.5)

    save_json(products, "products.json")
    return products


def extract_image_url(soup: BeautifulSoup) -> str:
    """제품 상세 페이지에서 대표 이미지 URL을 추출 (여러 셀렉터 시도)"""
    # 자주 쓰이는 셀렉터 후보들
    candidates = [
        "div.view img",
        "div.product-image img",
        "div.product_img img",
        "div.thumb img",
        ".product-detail img",
        "div.view div img",
    ]

    for selector in candidates:
        img_el = soup.select_one(selector)
        if img_el:
            src = img_el.get("src") or img_el.get("data-src") or ""
            if src and not src.startswith("data:"):
                # 상대경로 → 절대경로 변환
                return urljoin(BASE_URL, src)

    # 마지막 fallback: og:image 메타 태그
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(BASE_URL, og["content"])

    return ""


def crawl_product_detail(url: str, category: str) -> dict | None:
    soup = get_soup(url)
    if not soup:
        return None

    # 제품명
    name_el = soup.select_one("div.view h3")
    name = name_el.get_text(strip=True) if name_el else ""

    # 제품 설명
    desc_el = soup.select_one("div.product-explanation")
    description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

    # 영양정보
    nutrition = {}
    nutrition_div = soup.select_one("div.product-nutrition")
    if nutrition_div:
        rows = nutrition_div.find_all("tr")
        for row in rows:
            cols = row.find_all(["th", "td"])
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True)
                val = cols[1].get_text(strip=True)
                if key and val:
                    nutrition[key] = val

    # 제품 추가 정보
    info_el = soup.select_one("div.product-info")
    info = info_el.get_text(separator=" ", strip=True) if info_el else ""

    # ✅ 이미지 URL 추출 (신규 추가)
    image_url = extract_image_url(soup)

    if not name:
        return None

    return {
        "category": category,
        "name": name,
        "description": description,
        "info": info,
        "nutrition": nutrition,
        "image_url": image_url,   # ← 신규 필드
        "url": url,
    }


# ────────────────────────────────────────────
# 2. FAQ 크롤링
# ────────────────────────────────────────────
def crawl_faq() -> list[dict]:
    print("\n[2/3] FAQ 크롤링 시작...")
    faqs = []

    for page in range(1, 6):
        url = f"{BASE_URL}/mobile/cs/faq_list.sm?page={page}"
        print(f"  FAQ 페이지 {page}")
        soup = get_soup(url)
        if not soup:
            break

        items = soup.select("dl dt, .faq_list li, .faq dt, li.faq_item")

        if not items:
            text = soup.get_text(separator="\n")
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                if line.startswith("Q") and len(line) > 3:
                    question = line.lstrip("Q.").lstrip("Q:").strip()
                    answer = ""
                    if i + 1 < len(lines) and lines[i + 1].startswith("A"):
                        answer = lines[i + 1].lstrip("A.").lstrip("A:").strip()
                    if question:
                        faqs.append({"question": question, "answer": answer})
            break

        found = False
        for item in items:
            q_el = item.select_one(".q_txt, strong, span") or item
            question = q_el.get_text(strip=True).lstrip("Q.").lstrip("Q:").strip()
            a_el = item.find_next_sibling("dd")
            answer = a_el.get_text(strip=True).lstrip("A.").lstrip("A:").strip() if a_el else ""

            if question and len(question) > 5:
                faqs.append({"question": question, "answer": answer})
                found = True

        time.sleep(0.5)
        if not found:
            break

    save_json(faqs, "faq.json")
    return faqs


# ────────────────────────────────────────────
# 3. 레시피 (샘플 데이터)
# ────────────────────────────────────────────
def crawl_recipes() -> list[dict]:
    print("\n[3/3] 레시피 데이터 저장 중...")
    recipes = [
        {
            "title": "딸기우유 젤리",
            "ingredients": "서울우유 딸기우유 200ml, 젤라틴 5g, 설탕 1큰술",
            "steps": ["젤라틴을 찬물에 불린다", "딸기우유를 따뜻하게 데운다", "젤라틴을 녹여 섞는다", "냉장고에 2시간 굳힌다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "우유 팬케이크",
            "ingredients": "서울우유 200ml, 밀가루 200g, 달걀 2개, 버터 30g, 설탕 2큰술, 베이킹파우더 1작은술",
            "steps": ["밀가루, 베이킹파우더, 설탕을 체에 친다", "달걀과 우유를 섞는다", "가루류를 넣고 반죽한다", "버터를 두른 팬에 구워낸다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "우유 카레",
            "ingredients": "서울우유 300ml, 카레 가루 3큰술, 감자 2개, 당근 1개, 양파 1개, 닭고기 200g",
            "steps": ["채소와 고기를 먹기 좋게 자른다", "팬에 볶는다", "물 500ml와 우유를 넣고 끓인다", "카레 가루를 넣고 15분 더 끓인다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "우유 미숫가루",
            "ingredients": "서울우유 200ml, 미숫가루 3큰술, 꿀 1큰술",
            "steps": ["차가운 우유에 미숫가루를 넣는다", "꿀을 추가한다", "잘 저어서 마신다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "버터 팬케이크",
            "ingredients": "서울우유 무염버터 30g, 우유 200ml, 밀가루 150g, 달걀 2개, 설탕 2큰술",
            "steps": ["버터를 녹인다", "달걀, 우유, 설탕을 섞는다", "밀가루를 넣고 반죽한다", "버터 두른 팬에 노릇하게 굽는다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "크림 수프",
            "ingredients": "서울우유 생크림 200ml, 우유 200ml, 버섯 100g, 양파 1/2개, 버터 20g, 소금 약간",
            "steps": ["버터에 양파와 버섯을 볶는다", "우유와 생크림을 넣고 끓인다", "소금으로 간한다", "블렌더로 갈아서 완성"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "치즈 토스트",
            "ingredients": "서울우유 체다치즈 2장, 식빵 2장, 버터 10g",
            "steps": ["식빵에 버터를 바른다", "치즈를 올린다", "에어프라이어 180도에서 5분 굽는다"],
            "url": "https://m.seoulmilk.co.kr",
        },
        {
            "title": "우유 라떼",
            "ingredients": "서울우유 200ml, 에스프레소 1샷, 설탕 1작은술",
            "steps": ["우유를 스팀으로 데운다", "에스프레소를 추출한다", "컵에 우유를 먼저 붓고 에스프레소를 넣는다"],
            "url": "https://m.seoulmilk.co.kr",
        },
    ]
    save_json(recipes, "recipes.json")
    return recipes


# ────────────────────────────────────────────
# 실행
# ────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("서울우유 데이터 크롤링 시작")
    print("=" * 50)

    products = crawl_products()
    faqs = crawl_faq()
    recipes = crawl_recipes()

    print("\n" + "=" * 50)
    print("크롤링 완료!")
    print(f"  제품:   {len(products)}건")
    print(f"  FAQ:    {len(faqs)}건")
    print(f"  레시피: {len(recipes)}건")
    print(f"  저장 위치: {OUTPUT_DIR}")
    print("=" * 50)
