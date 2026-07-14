#!/usr/bin/env python3
"""
Apple ID 中速爬虫 (GitHub Actions 终极版)
主攻 idfree.top。加入了你提供的 laomaos 后台接口直连，以及 Cloudflare 致命拦截诊断！
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

TARGET_SITES = [
    ("idfree.top", "https://idfree.top/", "美国"),
    ("svip.xxxy.info", "https://svip.xxxy.info/", "美国"),
    ("fanqiangnan.com", "https://fanqiangnan.com/appleid.html", "美国"),
    ("laosjid.com", "https://laosjid.com/", "混合区"),
    ("id.jincaii.com", "https://id.jincaii.com/", "美国"),
    ("ermao.net", "https://www.ermao.net/blog/freeappleid/", "混合区"),
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

# 你的心血代码，一字未删
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

def scroll_to_bottom_deep(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(8): 
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5) 
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height: break 
        last_height = new_height

def close_popups(driver):
    for sel in ["//button[contains(.,'知道')]", "//button[contains(.,'同意')]", "//button[contains(.,'关闭')]", "//*[@aria-label='Close']"]:
        try:
            btn = WebDriverWait(driver, 1.5).until(EC.element_to_be_clickable((By.XPATH, sel)))
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.5)
        except Exception: pass

def universal_extract(html: str, default_country: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    results, seen = [], set()

    for card in soup.select(".card-body, .card, .account-card, .col-md-6, .item, div[class*='account'], tr, li"):
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
        country = find_country(card.get_text(" ", strip=True)[:300]) or default_country
        seen.add(email)
        results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": country})

    if not results:
        matches = re.findall(r"copy(?:Text|ToClipboard|Account|Password)?\(['\"&quot;&#39;]+([^'\"&quot;&#39;]+)['\"&quot;&#39;]+\)", html)
        em_arr, pw_arr = [], []
        for m in matches:
            if "@" in m and "." in m: em_arr.append(m.lower())
            elif len(m) >= 4: pw_arr.append(m)
        for i in range(min(len(em_arr), len(pw_arr))):
            e, p = em_arr[i], pw_arr[i]
            if e not in seen:
                seen.add(e)
                results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": default_country})

    if not results:
        text = soup.get_text(" ", strip=True)
        for match in re.finditer(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text):
            e = match.group(1).lower()
            if e in seen: continue
            after = text[match.end():match.end()+150]
            pw_match = re.search(r'(?:密码|Pass|Pw|Pwd)[:：\s]*([A-Za-z0-9!@#$%^&*()_+\-=\[\]{}]{5,32})', after, re.I)
            if pw_match:
                p = pw_match.group(1).strip()
                seen.add(e)
                results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": default_country})

    return results

def crawl_idfree_top(driver) -> list:
    """idfree.top 终极强攻版"""
    logger.info("  [策略1] 尝试直接请求你发现的 laomaos 后台接口...")
    try:
        # 你给的“神仙线索”
        api_url = "https://aunlock.laomaos.com/shareapi/rnWQGxeMjZ/114466"
        resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            results = universal_extract(resp.text, "美国")
            if results:
                logger.info(f"  [接口偷家成功] idfree.top 提取到: {len(results)} 条")
                return results
    except Exception as e:
        logger.warning(f"  后台接口请求失败: {e}")

    logger.info("  [策略2] 启动 Selenium 强行渲染网页...")
    driver.get("https://idfree.top/")
    
    # 诊断核心：由于 GitHub Actions 使用的是云端IP，极易被 CF 拦截。强等 12 秒。
    time.sleep(12) 
    page_title = driver.title
    logger.info(f"  [诊断日志] 当前 idfree.top 网页标题为: {page_title}")
    
    if "Just a moment" in page_title or "Cloudflare" in page_title:
        logger.error("  [致命拦截] 发现 Cloudflare 5秒盾！GitHub Actions IP 已被网站保安物理拉黑，网页根本没加载出来！")
        return []

    # 疯狂寻找你写的按钮
    for xpath in ["//button[contains(.,'阅读')]", "//button[contains(.,'继续查看')]", "//button[contains(.,'同意')]"]:
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            driver.execute_script("arguments[0].click();", btn)
            logger.info("  [操作] 成功点击了确认按钮！")
            time.sleep(2)
        except Exception: pass
        
    close_popups(driver)
    scroll_to_bottom_deep(driver)
    results = universal_extract(driver.page_source, "美国")
    
    # 你的终极Hook兜底
    if not results:
        logger.info("  [操作] 启动 HOOK_JS 剪贴板暴力劫持...")
        driver.execute_script(HOOK_JS)
        time.sleep(0.5)
        for btn in driver.find_elements(By.XPATH, "//button[contains(.,'复制')] | //a[contains(.,'复制')]")[:50]:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.15)
            except Exception: pass
        copied = driver.execute_script("return window.__copied||[]")
        es, ps = [c.lower() for c in copied if "@" in c and "." in c], [c for c in copied if "@" not in c and len(c)>=4]
        for i in range(min(len(es), len(ps))):
            if is_valid_email(es[i]): results.append({"email": es[i], "password": ps[i], "status": "正常", "checked_at": now_cst(), "country": "美国"})
            
    logger.info(f"  idfree.top 最终提取到: {len(results)} 条")
    return results

def crawl_site(driver, url, site_name, country):
    driver.get(url)
    time.sleep(8) # 增加等待时间破盾
    close_popups(driver)
    scroll_to_bottom_deep(driver)
    results = universal_extract(driver.page_source, country)
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
                if name == "idfree.top":
                    pairs = crawl_idfree_top(driver)
                else:
                    pairs = crawl_site(driver, url, name, country)
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
