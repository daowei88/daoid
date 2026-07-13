#!/usr/bin/env python3
"""
Apple ID 中速爬虫 — crawler_mid.py
负责站点（每 2 分钟爬一次）：
  1. idfree.top      — Selenium（保留原版：有"我已阅读"弹窗必须点击，剪贴板兜底）
  2. svip.xxxy.info  — 新增通用 Vue 卡片站
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

class _CSTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        cst = timezone(timedelta(hours=8))
        ct = datetime.fromtimestamp(record.created, tz=cst)
        return ct.strftime('%Y-%m-%d %H:%M:%S')
for _h in logging.root.handlers:
    _h.setFormatter(_CSTFormatter('%(asctime)s [%(levelname)s] %(message)s'))

CST = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

VALID_DOMAINS = {
    "icloud.com", "me.com", "mac.com", "gmail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "qq.com", "163.com", "126.com", "yahoo.com", "yahoo.co.jp",
    "protonmail.com", "proton.me", "email.com",
}

COUNTRY_RE = re.compile(r"(美国|英国|日本|香港|台湾|韩国|越南|澳大利亚|新加坡|加拿大|小火箭)")

MID_SOURCES = {"idfree.top", "svip.xxxy.info"}

SITE_ORDER = [
    "applexp/美区", "applexp/日区", "applexp/港区", "applexp/小火箭",
    "fanqiangnan.com", "id.jincaii.com", "laosjid.com", "free.iosapp.icu", "ermao.net",
    "idfree.top", "svip.xxxy.info", "tkbaohe.com", "id.btvda.top"
]

def is_valid_email(email: str) -> bool:
    if not email or "@" not in email: return False
    parts = email.lower().split("@")
    return len(parts) == 2 and len(parts[0]) >= 2

def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
def find_country(text: str) -> str:
    m = COUNTRY_RE.search(text or "")
    return m.group(1) if m else "美国"

def dedup(lst):
    seen, out = set(), []
    for r in lst:
        e = r.get("email", "").lower().strip()
        if e and e not in seen and is_valid_email(e):
            seen.add(e)
            out.append(r)
    return out

def fetch_html(url: str, timeout: int = 12) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = "utf-8"
        return resp.text if resp.status_code == 200 else ""
    except Exception: return ""

def make_driver():
    import tempfile
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--single-process")
    opts.add_argument("--no-zygote")           
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    return driver

def scroll(driver, n=8):
    for _ in range(n):
        driver.execute_script("window.scrollBy(0,700);")
        time.sleep(0.5)

def close_popups(driver):
    selectors = [
        "//button[contains(.,'知道了')]", "//button[contains(.,'我知道了')]",
        "//button[contains(.,'同意')]", "//button[contains(.,'确认')]",
        "//button[contains(.,'确定')]", "//button[contains(.,'关闭')]",
        "//button[contains(.,'Close')]", "//a[contains(.,'我知道了')]",
        "//div[contains(@class,'modal')]//button", "//div[contains(@class,'dialog')]//button",
        "//div[contains(@class,'popup')]//button", "//*[@aria-label='Close']",
        "//*[contains(@class,'close-btn')]",
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, sel)))
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.5)
        except Exception: pass

HOOK_JS = r"""
window.__copied = window.__copied || [];
try {
    var _orig = navigator.clipboard.writeText.bind(navigator.clipboard);
    navigator.clipboard.writeText = function(text){
        window.__copied.push(text);
        return _orig(text);
    };
} catch(e) {}
document.addEventListener('copy', function(e){
    try{
        var t = e.clipboardData && e.clipboardData.getData('text');
        if(t) window.__copied.push(t);
    }catch(ex){}
}, true);
"""

def strategy_data_clipboard(html: str) -> list:
    """idfree.top 与 svip.xxxy.info 通用解析"""
    soup = BeautifulSoup(html, "lxml")
    results, seen = [], set()

    for btn in soup.select("button[id^='username_'], a[id^='username_']"):
        n = btn.get("id", "")[9:]
        email = btn.get("data-clipboard-text", "").strip().lower()
        if not is_valid_email(email) or email in seen: continue
        pw_btn = soup.select_one(f"#password_{n}")
        if not pw_btn: continue
        pw = pw_btn.get("data-clipboard-text", "").strip()
        if not pw or "@" in pw or len(pw) < 4: continue
        card = btn.find_parent(class_="card-body") or btn.find_parent(class_="card")
        country = ""
        if card:
            for anc in card.parents:
                country = find_country(anc.get_text(" ", strip=True)[:300])
                if country: break
        seen.add(email)
        results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": country})
    if results: return results

    for card in soup.select(".card-body, .account-card"):
        email = ""
        for sel in [".copy-btn", "button.btn-primary[data-clipboard-text]", "button[data-copy]"]:
            b = card.select_one(sel)
            if b:
                v = (b.get("data-clipboard-text") or b.get("data-copy") or "").strip().lower()
                if is_valid_email(v):
                    email = v
                    break
        if not email or email in seen: continue
        pw = ""
        for sel in [".copy-pass-btn", "button.btn-success[data-clipboard-text]"]:
            b = card.select_one(sel)
            if b:
                v = b.get("data-clipboard-text", "").strip()
                if v and "@" not in v and 4 <= len(v) <= 64:
                    pw = v
                    break
        if not pw:
            for b in card.select("button[data-copy]"):
                v = b.get("data-copy", "").strip()
                if v and "@" not in v and 4 <= len(v) <= 64 and v != email:
                    pw = v
                    break
                    
        if not pw: continue
        country = ""
        for anc in card.parents:
            country = find_country(anc.get_text(" ", strip=True)[:300])
            if country: break
        seen.add(email)
        results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": country})
    return results

def crawl_idfree_top(driver) -> list:
    html = fetch_html("https://idfree.top/")
    if html and "@" in html:
        r = strategy_data_clipboard(html)
        if r:
            logger.info(f"  idfree.top [requests] → {len(r)} 条")
            return dedup(r)

    loaded = False
    for url in ["https://idfree.top/", "https://www.idfree.top/"]:
        try:
            driver.get(url)
            WebDriverWait(driver, 12).until(
                lambda d: d.execute_script("return document.readyState") == "complete")
            if len(driver.page_source) > 2000:
                loaded = True
                break
        except Exception: continue

    if not loaded: return []

    time.sleep(2)
    for xpath in [
        "//button[contains(.,'我已阅读')]",
        "//button[contains(.,'继续查看账号')]",
        "//button[contains(.,'继续查看')]",
        "//button[contains(.,'查看账号')]",
    ]:
        try:
            btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].click();", btn)
            logger.info(f"  idfree 点击: {btn.text.strip()}")
            time.sleep(2)
            break
        except Exception: pass
            
    close_popups(driver)
    scroll(driver, n=10)
    time.sleep(2)

    results = strategy_data_clipboard(driver.page_source)
    if not results:
        driver.execute_script(HOOK_JS)
        time.sleep(0.3)
        xpath_btns = (
            "//button[contains(.,'复制账号') or contains(.,'账号')]"
            " | //button[contains(.,'复制密码') or contains(.,'密码')]"
            " | //button[contains(.,'复制') and not(contains(.,'链接'))]"
        )
        btns = driver.find_elements(By.XPATH, xpath_btns)
        emails_list, pwds_list = [], []
        for btn in btns[:300]:
            try:
                before = len(driver.execute_script("return window.__copied||[]"))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.12)
                after = driver.execute_script("return window.__copied||[]")
                if len(after) > before:
                    val = after[-1].strip()
                    if "@" in val: emails_list.append(val.lower())
                    elif len(val) >= 5: pwds_list.append(val)
            except Exception: pass
        seen = set()
        for i in range(min(len(emails_list), len(pwds_list))):
            e, p = emails_list[i], pwds_list[i]
            if is_valid_email(e) and p and e not in seen and len(p) >= 5:
                seen.add(e)
                results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": "美国"})

    logger.info(f"  idfree.top 最终: {len(results)} 条")
    return dedup(results)

def crawl_svip(driver) -> list:
    try:
        driver.get("https://svip.xxxy.info/")
        time.sleep(5)
        close_popups(driver)
        scroll(driver, n=4)
        results = strategy_data_clipboard(driver.page_source)
        logger.info(f"  svip.xxxy.info 最终: {len(results)} 条")
        return dedup(results)
    except Exception as ex:
        logger.error(f"  svip 异常: {ex}")
        return []

def merge_and_save(mid_records: dict, output_path: str) -> dict:
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old = json.load(f)
            for a in old.get("accounts", []):
                if a.get("source", "") not in MID_SOURCES: merged[a["email"]] = a
        except Exception: pass

    for e, rec in mid_records.items(): merged[e] = rec
    groups = {}
    for a in merged.values(): groups.setdefault(a.get("source", "unknown"), []).append(a)
    for src in groups: groups[src].sort(key=lambda a: a.get("checked_at", "") or "", reverse=True)

    accounts = []
    for src in SITE_ORDER: accounts.extend(groups.get(src, []))
    for src, lst in groups.items():
        if src not in SITE_ORDER: accounts.extend(lst)

    source_stats = {}
    for a in accounts:
        src = a.get("source", "unknown")
        source_stats[src] = source_stats.get(src, 0) + 1

    result = {
        "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
        "total": len(accounts),
        "source_stats": source_stats,
        "accounts": accounts,
    }
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def crawl_mid():
    records, source_stats = {}, {}
    logger.info("【中速爬虫】启动 Chrome…")
    driver = make_driver()
    try:
        tasks = [("idfree.top", crawl_idfree_top), ("svip.xxxy.info", crawl_svip)]
        for name, fn in tasks:
            try:
                pairs = fn(driver)
            except Exception as ex:
                logger.error(f"  {name} 异常: {ex}")
                pairs = []

            nc = 0
            for p in pairs:
                e  = p.get("email", "").strip().lower()
                pw = p.get("password", "").strip()
                if e and pw and len(pw) >= 4:
                    if e not in records:
                        records[e] = {
                            "id": uid(e), "email": e, "password": pw,
                            "status": p.get("status", "正常"), "country": p.get("country", ""),
                            "checked_at": p.get("checked_at", now_cst()), "source": name, "updated_at": now_cst(),
                        }
                        nc += 1
            source_stats[name] = nc
            logger.info(f"  → 新增 {nc} 条")
    finally:
        driver.quit()
        logger.info("Chrome 已关闭")

    return records, source_stats

if __name__ == "__main__":
    output_path = os.environ.get("OUTPUT_FILE", "apple_ids.json")
    records, source_stats = crawl_mid()
    merge_and_save(records, output_path)
    logger.info("【中速爬虫完成】" + " ".join(f"{k}={v}" for k, v in source_stats.items()))