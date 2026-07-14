#!/usr/bin/env python3
"""
Apple ID 中速爬虫 (GitHub Actions 终极强拆版)
接管所有结构变动频繁、带有 5 秒盾或动态 JS 的站点。
"""

import re, json, time, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

COUNTRY_RE = re.compile(r"(美国|英国|日本|香港|台湾|韩国|澳大利亚|新加坡|加拿大|小火箭)")

# 目标接管列表
TARGET_SITES = [
    ("idfree.top", "https://idfree.top/", "美国"),
    ("svip.xxxy.info", "https://svip.xxxy.info/", "美国"),
    ("fanqiangnan.com", "https://fanqiangnan.com/appleid.html", "美国"),
    ("laosjid.com", "https://laosjid.com/", "混合区"),
    ("id.jincaii.com", "https://id.jincaii.com/", "美国"),
]

MID_SOURCES = {name for name, _, _ in TARGET_SITES}

def is_valid_email(email: str) -> bool: return "@" in str(email) and len(str(email).split("@")[0]) >= 2
def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
def find_country(text: str) -> str:
    m = COUNTRY_RE.search(text or "")
    return m.group(1) if m else "美国"

def make_driver():
    import tempfile
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    return driver

# 保留你最初最硬核的剪贴板劫持代码
HOOK_JS = r"""
window.__copied = window.__copied || [];
try {
    var _orig = navigator.clipboard.writeText.bind(navigator.clipboard);
    navigator.clipboard.writeText = function(text){ window.__copied.push(text); return _orig(text); };
} catch(e) {}
document.addEventListener('copy', function(e){
    try{ var t = e.clipboardData && e.clipboardData.getData('text'); if(t) window.__copied.push(t); }catch(ex){}
}, true);
"""

def close_popups(driver):
    """盲点：无视 DOM 结构，强制点击所有看着像弹窗确认的按钮"""
    for sel in ["//button[contains(.,'知道')]", "//button[contains(.,'同意')]", "//button[contains(.,'关闭')]", "//button[contains(.,'继续查看')]", "//button[contains(.,'我已阅读')]", "//*[@aria-label='Close']"]:
        try:
            btn = WebDriverWait(driver, 1.5).until(EC.element_to_be_clickable((By.XPATH, sel)))
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.5)
        except Exception: pass

def strategy_data_clipboard(html: str) -> list:
    """四维提取引擎：涵盖 data-clipboard, copyXXX 函数解析"""
    soup = BeautifulSoup(html, "lxml")
    results, seen = [], set()

    # 放宽匹配条件，只要是个块就行
    for card in soup.select(".card-body, .card, .account-card, .col-md-6, .item, div[class*='account']"):
        email, pw = "", ""
        for b in card.select("[data-clipboard-text], [data-copy], button"):
            v = (b.get("data-clipboard-text") or b.get("data-copy") or "").strip().lower()
            if not v and "copyAccount" in b.get("onclick", ""):
                m = re.search(r"copyAccount\(['\"]([^'\"]+)['\"]\)", b.get("onclick", ""))
                if m: v = m.group(1).strip().lower()
            if is_valid_email(v): email = v; break
            
        if not email or email in seen: continue

        for b in card.select("[data-clipboard-text], [data-copy], button"):
            v = (b.get("data-clipboard-text") or b.get("data-copy") or "").strip()
            if not v and "copyPassword" in b.get("onclick", ""):
                m = re.search(r"copyPassword\(['\"]([^'\"]+)['\"]\)", b.get("onclick", ""))
                if m: v = m.group(1).strip()
            if v and "@" not in v and 4 <= len(v) <= 64 and v != email: pw = v; break
                
        if not pw: continue
        country = find_country(card.get_text(" ", strip=True)[:300]) or "混合区"
        seen.add(email)
        results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": country})
    return results

def crawl_universal(driver, url, site_name, default_country):
    driver.get(url)
    time.sleep(6) # 强制等渲染
    driver.execute_script("window.scrollBy(0,800);")
    close_popups(driver)
    time.sleep(1)

    results = strategy_data_clipboard(driver.page_source)
    
    # 终极 HOOK 兜底计划 (针对完全不按套路出牌的站)
    if not results:
        driver.execute_script(HOOK_JS)
        time.sleep(0.5)
        # 强行把所有名字叫复制的按钮点一遍
        for btn in driver.find_elements(By.XPATH, "//button[contains(.,'复制')] | //a[contains(.,'复制')]")[:50]:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.15)
            except Exception: pass
            
        copied = driver.execute_script("return window.__copied||[]")
        es = [c.lower() for c in copied if "@" in c and "." in c]
        ps = [c for c in copied if "@" not in c and len(c)>=4]
        for i in range(min(len(es), len(ps))):
            if is_valid_email(es[i]): 
                results.append({"email": es[i], "password": ps[i], "status": "正常", "checked_at": now_cst(), "country": default_country})
                
    logger.info(f"  {site_name} 提取到: {len(results)} 条")
    return results

def merge_and_save(mid_records: dict, source_stats: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old = json.load(f)
            for a in old.get("accounts", []):
                src = a.get("source", "")
                if src in MID_SOURCES and source_stats.get(src, 0) == 0:
                    merged[a["email"]] = a  # 防丢机制
                elif src not in MID_SOURCES:
                    merged[a["email"]] = a
        except Exception: pass

    for e, rec in mid_records.items(): merged[e] = rec
    accounts = sorted(merged.values(), key=lambda a: a.get("checked_at", ""), reverse=True)
    result = {"generated_at": now_cst(), "total": len(accounts), "accounts": accounts}
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

def crawl_mid():
    records, source_stats = {}, {s: 0 for s in MID_SOURCES}
    driver = make_driver()
    try:
        for name, url, country in TARGET_SITES:
            logger.info(f"▶ 开始强拆: {name}")
            try:
                pairs = crawl_universal(driver, url, name, country)
                source_stats[name] = len(pairs)
                for p in pairs:
                    e = p["email"]
                    records[e] = {"id": uid(e), "email": e, "password": p["password"], "status": "正常", "country": p.get("country", country), "checked_at": now_cst(), "source": name, "updated_at": now_cst()}
            except Exception as ex: 
                logger.error(f"  {name} 异常: {ex}")
    finally:
        driver.quit()
    return records, source_stats

if __name__ == "__main__":
    records, stats = crawl_mid()
    merge_and_save(records, stats, os.environ.get("OUTPUT_FILE", "apple_ids.json"))
    logger.info(f"【中速组】完成，共抓取 {len(records)} 条")
