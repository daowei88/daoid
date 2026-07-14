#!/usr/bin/env python3
"""
Apple ID 极速爬虫 (GitHub Actions 终极防丢版)
专职负责纯静态直链，秒级执行。
"""

import re, json, hashlib, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

FAST_SOURCES = {"free.iosapp.icu"}

def is_valid_email(email: str) -> bool: return "@" in str(email) and len(str(email).split("@")[0]) >= 2
def uid(email): return hashlib.md5(email.lower().encode()).hexdigest()[:12]
def now_cst(): return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

def fetch_html(url: str, timeout: int = 15) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = "utf-8"
        return resp.text if resp.status_code == 200 else ""
    except Exception as e: return ""

def crawl_iosapp() -> list:
    """降维打击：直接请求后端隐藏的 TXT 文件"""
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
    return results

def merge_and_save(fast_records: dict, source_stats: dict, output_path: str):
    merged = {}
    if Path(output_path).exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f: old_data = json.load(f)
            for a in old_data.get("accounts", []):
                src = a.get("source", "")
                if src in FAST_SOURCES and source_stats.get(src, 0) == 0:
                    merged[a["email"]] = a # 防丢机制
                elif src not in FAST_SOURCES:
                    merged[a["email"]] = a
        except Exception: pass

    for e, rec in fast_records.items(): merged[e] = rec
    accounts = sorted(merged.values(), key=lambda a: a.get("checked_at", ""), reverse=True)
    result = {"generated_at": now_cst(), "total": len(accounts), "accounts": accounts}
    with open(output_path, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)

def crawl_fast():
    records, source_stats = {}, {s: 0 for s in FAST_SOURCES}
    tasks = [("free.iosapp.icu", crawl_iosapp)]
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
