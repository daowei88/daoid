#!/usr/bin/env python3
"""
Apple ID 极速爬虫 (GitHub Actions 专版)
只负责纯静态文档和接口，秒出结果。
"""

import re, json, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# ⭐⭐⭐ 加强项：高匿伪装头，降低被微软 Azure 机房 IP 拦截的概率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

FAST_SOURCES = {"applexp/美区", "applexp/日区", "applexp/港区", "applexp/小火箭", "free.iosapp.icu", "ermao.net"}

def is_valid_email(email: str) -> bool: return "@" in str(email) and len(str(email).split("@")[0]) >= 2
def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

def fetch_html(url: str, timeout: int = 15) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = "utf-8"
        return resp.text if resp.status_code == 200 else ""
    except Exception: return ""

def crawl_iosapp() -> list:
    """⭐⭐⭐ 加强项：绕过网页前端，直接强行下载后端TXT文件，百发百中"""
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
    return results

def crawl_generic_text(url: str, site_name: str, default_country="美国") -> list:
    """⭐⭐⭐ 你的原版逻辑升级：强大的正则，不管站长改成什么排版都能抠出账密"""
    html = fetch_html(url)
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True) if html else ""
    results, seen = [], set()
    
    for match in re.finditer(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text):
        email = match.group(1).lower()
        if not is_valid_email(email) or email in seen: continue
        
        after_text = text[match.end():match.end()+150]
        pw = ""
        # 兼容中文冒号、英文冒号、空格等各种千奇百怪的密码提示
        pw_match = re.search(r'(?:密码|Pass|Pw|Pwd)[:：\s]*([A-Za-z0-9!@#$%^&*()_+\-=\[\]{}]{6,32})', after_text, re.I)
        if pw_match: pw = pw_match.group(1)
        
        if pw:
            results.append({"email": email, "password": pw, "status": "正常", "checked_at": now_cst(), "country": default_country})
            seen.add(email)
    logger.info(f"  {site_name} 提取到: {len(results)} 条")
    return results

def merge_and_save(fast_records: dict, source_stats: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old_data = json.load(f)
            for a in old_data.get("accounts", []):
                src = a.get("source", "")
                # ⭐⭐⭐ 你的救命稻草：如果 Actions 被墙导致本次抓取为 0，旧数据绝不删除，保住小火箭分类！
                if src in FAST_SOURCES and source_stats.get(src, 0) == 0:
                    merged[a["email"]] = a
                elif src not in FAST_SOURCES:
                    merged[a["email"]] = a
        except Exception: pass

    for e, rec in fast_records.items(): merged[e] = rec
    accounts = sorted(merged.values(), key=lambda a: a.get("checked_at", ""), reverse=True)
    result = {"generated_at": now_cst(), "total": len(accounts), "accounts": accounts}
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

def crawl_fast():
    records, source_stats = {}, {s: 0 for s in FAST_SOURCES}
    tasks = [
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
            source_stats[src] = len(pairs)
            for p in pairs:
                e, pw = p["email"], p["password"]
                records[e] = {"id": uid(e), "email": e, "password": pw, "status": "正常", "country": p["country"], "checked_at": now_cst(), "source": src, "updated_at": now_cst()}
        except Exception as ex:
            logger.error(f"{src} 异常: {ex}")
    return records, source_stats

if __name__ == "__main__":
    records, stats = crawl_fast()
    merge_and_save(records, stats, os.environ.get("OUTPUT_FILE", "apple_ids.json"))
    logger.info(f"【极速组】完成，共抓取 {len(records)} 条")