#!/usr/bin/env python3
"""
Apple ID 慢速爬虫 (GitHub Actions 终极防丢版)
包含: tkbaohe.com (Cloudflare 解密), id.btvda.top (深层滚动 API 拦截)
"""

import re, json, time, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

SLOW_SOURCES = {"tkbaohe.com", "id.btvda.top"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

def is_valid_email(email: str) -> bool: return "@" in str(email) and len(str(email).split("@")[0]) >= 2
def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

def make_driver():
    import tempfile
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    return driver

def decode_cfemail(encoded: str) -> str:
    try:
        enc = bytes.fromhex(encoded)
        return "".join(chr(b ^ enc[0]) for b in enc[1:])
    except Exception: return ""

def strategy_tkbaohe(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select(".card-body"):
        email = ""
        cf = card.select_one(".__cf_email__")
        if cf and cf.get("data-cfemail"): email = decode_cfemail(cf.get("data-cfemail")).lower()
        if not is_valid_email(email): continue

        pw = ""
        for btn in card.select("button"):
            oc = btn.get("onclick", "")
            if oc:
                m = re.search(r"copy\(['\"]([^'\"]{4,64})['\"]\)", oc)
                if m and "@" not in m.group(1): pw = m.group(1).strip()
        if not pw: continue

        results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": "小火箭"})
    return results

def crawl_tkbaohe(driver) -> list:
    driver.get("https://tkbaohe.com/Shadowrocket/")
    time.sleep(8) 
    driver.execute_script("window.scrollBy(0,1000);")
    time.sleep(2)
    results = strategy_tkbaohe(driver.page_source)
    logger.info(f"  tkbaohe 提取到: {len(results)} 条")
    return results

# 深度 API 网络拦截网
INTERCEPT_JS = r"""
window.__api_responses = [];
const _origFetch = window.fetch;
window.fetch = function() {
    var args = arguments;
    return _origFetch.apply(this, args).then(function(resp) {
        resp.clone().json().then(function(data) { window.__api_responses.push(data); }).catch(function(){});
        return resp;
    });
};
"""

def scroll_to_bottom_deep(driver):
    """深层触底：触发懒加载的隐藏 API 数据包"""
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(8): 
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2) 
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def crawl_btvda(driver) -> list:
    try:
        resp = requests.get("https://appleapi.omofunz.com/api/data", headers=HEADERS, timeout=10)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            results = [{"email": i.get("username", "").lower(), "password": i.get("password", ""), "status": "正常", "checked_at": now_cst(), "country": "美国"} for i in resp.json() if i.get("status") == 1]
            if results:
                logger.info(f"  btvda API提取到: {len(results)} 条")
                return results
    except Exception: pass

    try:
        driver.get("about:blank")
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": INTERCEPT_JS})
        driver.get("https://id.btvda.top/")
        time.sleep(6)
        
        scroll_to_bottom_deep(driver)
        
        raw_list = driver.execute_script("return window.__api_responses || []")
        results_map = {}
        for data in raw_list:
            if isinstance(data, list) and len(data)>0 and "username" in data[0]:
                for i in data:
                    if i.get("status") == 1:
                        e = i.get("username", "").lower()
                        p = i.get("password", "")
                        if e and p:
                            results_map[e] = {"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": "美国"}
                            
        results = list(results_map.values())
        logger.info(f"  btvda Selenium 拦截提取到: {len(results)} 条")
        return results
    except Exception as e:
        logger.error(f"  btvda 拦截失败: {e}")
    return []

def merge_and_save(slow_records: dict, source_stats: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old = json.load(f)
            for a in old.get("accounts", []):
                src = a.get("source", "")
                if src in SLOW_SOURCES and source_stats.get(src, 0) == 0:
                    merged[a["email"]] = a # 防丢机制
                elif src not in SLOW_SOURCES:
                    merged[a["email"]] = a
        except Exception: pass

    for e, rec in slow_records.items(): merged[e] = rec
    accounts = sorted(merged.values(), key=lambda a: a.get("checked_at", ""), reverse=True)
    result = {"generated_at": now_cst(), "total": len(accounts), "accounts": accounts}
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

def crawl_slow():
    records, source_stats = {}, {s: 0 for s in SLOW_SOURCES}
    driver = make_driver()
    try:
        tasks = [("tkbaohe.com", crawl_tkbaohe), ("id.btvda.top", crawl_btvda)]
        for name, fn in tasks:
            try:
                pairs = fn(driver)
                source_stats[name] = len(pairs)
                for p in pairs:
                    e = p["email"]
                    records[e] = {"id": uid(e), "email": e, "password": p["password"], "status": "正常", "country": p["country"], "checked_at": now_cst(), "source": name, "updated_at": now_cst()}
            except Exception as ex: logger.error(f"{name} 异常: {ex}")
    finally:
        driver.quit()
    return records, source_stats

if __name__ == "__main__":
    records, stats = crawl_slow()
    merge_and_save(records, stats, os.environ.get("OUTPUT_FILE", "apple_ids.json"))
    logger.info(f"【慢速组】完成，共抓取 {len(records)} 条")
