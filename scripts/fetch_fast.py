#!/usr/bin/env python3
"""
Apple ID 快速爬虫 — crawler_fast.py
负责高频更新站点（每 1 分钟爬一次）：
纯 requests 提取，无需无头浏览器，秒级完成。
"""

import re, json, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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

VALID_DOMAINS = {"icloud.com", "me.com", "mac.com", "gmail.com", "outlook.com", "hotmail.com", "live.com", "qq.com", "163.com", "yahoo.com", "proton.me", "email.com"}
COUNTRY_RE = re.compile(r"(美国|英国|日本|香港|台湾|韩国|越南|澳大利亚|新加坡|加拿大|小火箭)")

FAST_SOURCES = {
    "applexp/美区", "applexp/日区", "applexp/港区", "applexp/小火箭",
    "fanqiangnan.com", "id.jincaii.com", "laosjid.com", "free.iosapp.icu", "ermao.net"
}

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

def fetch_html(url: str, timeout: int = 10) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = "utf-8"
        return resp.text if resp.status_code == 200 else ""
    except Exception: return ""

# ── 专项解析器 ────────────────────────────────────────────────

def crawl_fanqiang_and_jincaii(url: str, site_name: str) -> list:
    """针对 fanqiangnan.com 和 id.jincaii.com (解析 onclick 属性)"""
    html = fetch_html(url)
    results = []
    matches = re.findall(r"copy(?:Text|ToClipboard)\('([^']+)'", html)
    seen = set()
    for i in range(0, len(matches)-1, 2):
        email, pwd = matches[i].strip(), matches[i+1].strip()
        if is_valid_email(email) and len(pwd) >= 4 and "@" not in pwd:
            if email not in seen:
                results.append({"email": email, "password": pwd, "status": "正常", "checked_at": now_cst(), "country": "美国"})
                seen.add(email)
    logger.info(f"  {site_name} 提取到: {len(results)} 条")
    return dedup(results)

def crawl_laosjid() -> list:
    """针对 laosjid.com (分别解析 copyAccount 和 copyPassword)"""
    html = fetch_html("https://laosjid.com/")
    results = []
    accounts = re.findall(r"copyAccount\('([^']+)'\)", html)
    passwords = re.findall(r"copyPassword\('([^']+)'\)", html)
    for i in range(min(len(accounts), len(passwords))):
        e, p = accounts[i].strip().lower(), passwords[i].strip()
        if is_valid_email(e) and len(p) >= 4:
            results.append({"email": e, "password": p, "status": "正常", "checked_at": now_cst(), "country": "混合区"})
    logger.info(f"  laosjid.com 提取到: {len(results)} 条")
    return dedup(results)

def crawl_iosapp() -> list:
    """针对 free.iosapp.icu (降维打击：直接请求后端 TXT 文件)"""
    results = []
    for i in range(1, 4):
        text = fetch_html(f"https://free.iosapp.icu/go-rod/{i}.txt")
        if text:
            email, pwd = "", ""
            for line in text.splitlines():
                if "账号:" in line: email = line.split("账号:")[-1].strip().lower()
                if "密码:" in line: pwd = line.split("密码:")[-1].strip()
            if is_valid_email(email) and pwd:
                results.append({"email": email, "password": pwd, "status": "正常", "checked_at": now_cst(), "country": "美国"})
    logger.info(f"  free.iosapp.icu 提取到: {len(results)} 条")
    return dedup(results)

def crawl_generic_text(url: str, site_name: str, default_country="美国") -> list:
    """针对 applexp 和 ermao.net 等静态文档/博客"""
    html = fetch_html(url)
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True) if html else ""
    results, seen = [], set()
    email_pattern = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
    
    for match in email_pattern.finditer(text):
        email = match.group(1).lower()
        if not is_valid_email(email) or email in seen: continue
        after_text = text[match.end():match.end()+150]
        pw = ""
        pw_match = re.search(r'(?:密码|Pass|Pw)[^\w]*([A-Za-z0-9!@#$%^&*()_+\-=\[\]{}]{6,32})', after_text, re.I)
        if pw_match: pw = pw_match.group(1)
        if pw:
            results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": default_country})
            seen.add(email)
    logger.info(f"  {site_name} 提取到: {len(results)} 条")
    return dedup(results)

# ── 任务分配与合并 ────────────────────────────────────────────────

def merge_and_save(fast_records: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old = json.load(f)
            for a in old.get("accounts", []):
                if a.get("source", "") not in FAST_SOURCES: merged[a["email"]] = a
        except Exception: pass
    for e, rec in fast_records.items(): merged[e] = rec

    groups = {}
    for a in merged.values(): groups.setdefault(a.get("source", "unknown"), []).append(a)
    for src in groups: groups[src].sort(key=lambda x: x.get("checked_at", ""), reverse=True)
    
    accounts = []
    for src in SITE_ORDER: accounts.extend(groups.get(src, []))
    for src, lst in groups.items(): 
        if src not in SITE_ORDER: accounts.extend(lst)

    result = {
        "generated_at": now_cst(), "total": len(accounts),
        "source_stats": {a.get("source", "unknown"): 0 for a in accounts},
        "accounts": accounts
    }
    for a in accounts: result["source_stats"][a.get("source", "unknown")] += 1
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

def crawl_fast():
    records, source_stats = {}, {}
    tasks = [
        ("fanqiangnan.com", lambda: crawl_fanqiang_and_jincaii("https://fanqiangnan.com/appleid.html", "fanqiangnan.com")),
        ("id.jincaii.com", lambda: crawl_fanqiang_and_jincaii("https://id.jincaii.com/", "id.jincaii.com")),
        ("laosjid.com", crawl_laosjid),
        ("free.iosapp.icu", crawl_iosapp),
        ("ermao.net", lambda: crawl_generic_text("https://www.ermao.net/blog/freeappleid/", "ermao.net", "混合区")),
        ("applexp/美区", lambda: crawl_generic_text("https://docs.applexp.com/free-accounts/appleid-us", "applexp/美区", "美国")),
        ("applexp/日区", lambda: crawl_generic_text("https://docs.applexp.com/free-accounts/appleid-jp", "applexp/日区", "日本")),
        ("applexp/港区", lambda: crawl_generic_text("https://docs.applexp.com/free-accounts/appleid-hk", "applexp/港区", "香港")),
        ("applexp/小火箭", lambda: crawl_generic_text("https://docs.applexp.com/free-accounts/Shadowrocket", "applexp/小火箭", "小火箭")),
    ]
    for src, fn in tasks:
        try:
            pairs = fn()
            for p in pairs:
                e, pw = p["email"], p["password"]
                records[e] = {"id": uid(e), "email": e, "password": pw, "status": "正常", "country": p["country"], "checked_at": now_cst(), "source": src, "updated_at": now_cst()}
            source_stats[src] = len(pairs)
        except Exception as ex:
            logger.error(f"{src} 抓取异常: {ex}")
    return records, source_stats

if __name__ == "__main__":
    records, stats = crawl_fast()
    merge_and_save(records, os.environ.get("OUTPUT_FILE", "apple_ids.json"))
    logger.info(f"【极速爬虫完成】写入 {len(records)} 条新记录")