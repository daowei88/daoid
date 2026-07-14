#!/usr/bin/env python3
"""
Apple ID 中速爬虫 (GitHub Actions 终极强拆版)
负责接管所有结构复杂、带有 5 秒盾或动态 JS 的顽固站点。
采用“四维全频段提取”逻辑，无视 DOM 结构变化。
"""

import re, json, time, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# 我们要强攻的所有目标站点
TARGET_SITES = [
    ("idfree.top", "https://idfree.top/", "美国"),
    ("svip.xxxy.info", "https://svip.xxxy.info/", "美国"),
    ("fanqiangnan.com", "https://fanqiangnan.com/appleid.html", "美国"),
    ("laosjid.com", "https://laosjid.com/", "混合区"),
    ("id.jincaii.com", "https://id.jincaii.com/", "美国"),
    ("ermao.net", "https://www.ermao.net/blog/freeappleid/", "混合区"),
    ("applexp/美区", "https://docs.applexp.com/free-accounts/appleid-us", "美国"),
    ("applexp/日区", "https://docs.applexp.com/free-accounts/appleid-jp", "日本"),
    ("applexp/港区", "https://docs.applexp.com/free-accounts/appleid-hk", "香港"),
    ("applexp/小火箭", "https://docs.applexp.com/free-accounts/Shadowrocket", "小火箭"),
]

MID_SOURCES = {name for name, _, _ in TARGET_SITES}

def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

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

def universal_extract(driver, url, site_name, default_country):
    """最强万能提取器：四层逻辑强拆"""
    results = []
    seen = set()

    # ==========================================
    # 第一层：直捣黄龙 (尝试直接请求隐藏的 API)
    # ==========================================
    try:
        parsed = urlparse(url)
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/data"
        resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    e = str(item.get("email") or item.get("username") or "").strip().lower()
                    p = str(item.get("password") or item.get("pwd") or "").strip()
                    if "@" in e and "." in e and len(p) >= 4:
                        c = item.get("country", default_country)
                        if e not in seen:
                            seen.add(e)
                            results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": c})
                if results:
                    logger.info(f"  {site_name} [第1层 API直连] -> {len(results)}条")
                    return results
    except Exception: pass

    # ==========================================
    # 如果 API 被拦截，启动 Selenium 进行后续三层打击
    # ==========================================
    try:
        driver.get(url)
        time.sleep(6) # 等待 Cloudflare 5秒盾和 Ajax 加载
        
        # 盲点：无视 DOM 结构，强制点击所有看着像“验证/继续”的按钮
        for btn in driver.find_elements(By.XPATH, "//button | //a"):
            txt = btn.text
            if any(k in txt for k in ["阅读", "继续", "知道", "关闭", "Agree", "Close"]):
                try: driver.execute_script("arguments[0].click();", btn)
                except: pass
        time.sleep(2)
        
        html = driver.page_source
        soup = BeautifulSoup(html, "lxml")
        
        # ==========================================
        # 第二层：属性爆破 (扫描所有剪贴板属性)
        # ==========================================
        emails_attr, pwds_attr = [], []
        for el in soup.select("[data-clipboard-text], [data-copy]"):
            val = (el.get("data-clipboard-text") or el.get("data-copy") or "").strip()
            if "@" in val and "." in val: emails_attr.append(val.lower())
            elif len(val) >= 4 and "@" not in val: pwds_attr.append(val)
            
        for i in range(min(len(emails_attr), len(pwds_attr))):
            e, p = emails_attr[i], pwds_attr[i]
            if e not in seen:
                seen.add(e)
                results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": default_country})
                
        # ==========================================
        # 第三层：源码强扣 (专治 laosjid 把密码写在 onClick 里)
        # ==========================================
        if not results:
            matches = re.findall(r"copy(?:Text|ToClipboard|Account|Password)?\(['\"]([^'\"]+)['\"]\)", html)
            em_arr, pw_arr = [], []
            for m in matches:
                if "@" in m and "." in m: em_arr.append(m.lower())
                elif len(m) >= 4: pw_arr.append(m)
            for i in range(min(len(em_arr), len(pw_arr))):
                e, p = em_arr[i], pw_arr[i]
                if e not in seen:
                    seen.add(e)
                    results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": default_country})
        
        # ==========================================
        # 第四层：纯文本透视 (专治 applexp 和 ermao 等博客)
        # ==========================================
        if not results:
            text = soup.get_text(" ", strip=True)
            for match in re.finditer(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text):
                e = match.group(1).lower()
                if e in seen: continue
                after = text[match.end():match.end()+150]
                # 兼容中英文冒号、空格，直接往后抓取密码
                pw_match = re.search(r'(?:密码|Pass|Pw|Pwd)[:：\s]*([A-Za-z0-9!@#$%^&*()_+\-=\[\]{}]{5,32})', after, re.I)
                if pw_match:
                    p = pw_match.group(1).strip()
                    seen.add(e)
                    results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": default_country})
                    
        logger.info(f"  {site_name} [Selenium 强拆成功] -> {len(results)}条")
    except Exception as e:
        logger.error(f"  {site_name} [提取失败]: {e}")
        
    return results

def crawl_mid():
    records, source_stats = {}, {s: 0 for s in MID_SOURCES}
    driver = make_driver()
    try:
        for name, url, country in TARGET_SITES:
            logger.info(f"▶ 开始强拆: {name}")
            pairs = universal_extract(driver, url, name, country)
            source_stats[name] = len(pairs)
            for p in pairs:
                e = p["email"]
                records[e] = {"id": uid(e), "email": e, "password": p["password"], "status": "正常", "country": p["country"], "checked_at": now_cst(), "source": name, "updated_at": now_cst()}
    finally:
        driver.quit()
    return records, source_stats

def merge_and_save(mid_records: dict, source_stats: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old = json.load(f)
            for a in old.get("accounts", []):
                src = a.get("source", "")
                # 防丢失机制：如果被墙导致本次抓取为 0，保留旧数据
                if src in MID_SOURCES and source_stats.get(src, 0) == 0:
                    merged[a["email"]] = a
                elif src not in MID_SOURCES:
                    merged[a["email"]] = a
        except Exception: pass

    for e, rec in mid_records.items(): merged[e] = rec
    accounts = sorted(merged.values(), key=lambda a: a.get("checked_at", ""), reverse=True)
    result = {"generated_at": now_cst(), "total": len(accounts), "accounts": accounts}
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    records, stats = crawl_mid()
    merge_and_save(records, stats, os.environ.get("OUTPUT_FILE", "apple_ids.json"))
    logger.info(f"【中速组】全频段打击完成，共抓取 {len(records)} 条")
