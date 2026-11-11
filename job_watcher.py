#!/usr/bin/env python3
"""
Job Watcher — checks company career pages for positions you care about
and alerts you when NEW matching postings appear.

Usage:
    python job_watcher.py            # run one check
    python job_watcher.py --loop     # keep running, check every hour
    python job_watcher.py --reset    # forget previously seen jobs
"""

import argparse
import hashlib
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.yaml"
SEEN_FILE = BASE_DIR / "seen_jobs.json"
LOG_FILE = BASE_DIR / "job_watcher.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------- helpers
def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(f"Config file not found: {CONFIG_FILE}")
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2), encoding="utf-8")


def job_id(company: str, title: str, link: str) -> str:
    return hashlib.sha1(f"{company}|{title.lower()}|{link}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------- fetching
def fetch_html(url: str, use_browser: bool) -> str:
    """Get page HTML. use_browser=True renders JavaScript (needs Playwright)."""
    if use_browser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "This site needs 'js: true' but Playwright isn't installed. "
                "Run: pip install playwright && playwright install chromium"
            )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
            browser.close()
            return html

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def extract_candidates(html: str, base_url: str) -> list[dict]:
    """Pull out text snippets that could be job titles (links, headings, list items)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    found, seen_text = [], set()
    for el in soup.find_all(["a", "h1", "h2", "h3", "h4", "h5", "li", "td", "strong"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not (3 <= len(text) <= 150) or text.lower() in seen_text:
            continue
        seen_text.add(text.lower())
        link_el = el if el.name == "a" else el.find("a") or el.find_parent("a")
        href = link_el.get("href") if link_el else None
        link = urljoin(base_url, href) if href else base_url
        found.append({"title": text, "link": link})
    return found


def matches(text: str, keywords: list[str], exclude: list[str]) -> bool:
    t = text.lower()
    if any(x.lower() in t for x in exclude):
        return False
    return any(re.search(r"\b" + re.escape(k.lower()) + r"\b", t) for k in keywords)


# ---------------------------------------------------------------- alerts
def notify(new_jobs: list[dict], cfg: dict) -> None:
    if not new_jobs:
        return

    lines = [f"• {j['company']}: {j['title']}\n  {j['link']}" for j in new_jobs]
    body = f"{len(new_jobs)} new matching job(s) found:\n\n" + "\n\n".join(lines)
    log(body)

    alerts = cfg.get("alerts", {}) or {}

    # Phone push notification via ntfy.sh (free, no account needed).
    # On GitHub, set the NTFY_TOPIC secret instead of putting it in config.yaml.
    ntfy = os.environ.get("NTFY_TOPIC") or alerts.get("ntfy_topic")
    if ntfy:
        try:
            requests.post(
                f"https://ntfy.sh/{ntfy}",
                data=body.encode("utf-8"),
                headers={"Title": f"{len(new_jobs)} new job match(es)", "Tags": "briefcase"},
                timeout=15,
            )
            log("Push notification sent.")
        except Exception as e:
            log(f"Push notification failed: {e}")

    # Email (Gmail: use an App Password, not your normal password)
    em = dict(alerts.get("email") or {})
    # On GitHub, EMAIL_FROM / EMAIL_TO / EMAIL_PASSWORD secrets switch email on.
    if os.environ.get("EMAIL_PASSWORD"):
        em.update(
            enabled=True,
            password=os.environ["EMAIL_PASSWORD"],
            **{"from": os.environ.get("EMAIL_FROM", em.get("from"))},
            to=os.environ.get("EMAIL_TO") or os.environ.get("EMAIL_FROM", em.get("to")),
        )
    if em.get("enabled"):
        try:
            msg = MIMEText(body)
            msg["Subject"] = f"Job Watcher: {len(new_jobs)} new match(es)"
            msg["From"] = em["from"]
            msg["To"] = em["to"]
            with smtplib.SMTP(em.get("smtp_server", "smtp.gmail.com"), em.get("smtp_port", 587)) as s:
                s.starttls()
                s.login(em["from"], em["password"])
                s.send_message(msg)
            log("Email sent.")
        except Exception as e:
            log(f"Email failed: {e}")


# ---------------------------------------------------------------- main check
def run_check() -> None:
    cfg = load_config()
    seen = load_seen()
    global_kw = cfg.get("keywords", []) or []
    exclude = cfg.get("exclude", []) or []
    new_jobs = []

    for c in cfg.get("companies", []) or []:
        name, url = c.get("name"), c.get("url")
        if not name or not url:
            continue
        keywords = (c.get("keywords") or []) + global_kw
        try:
            html = fetch_html(url, use_browser=c.get("js", False))
            candidates = extract_candidates(html, url)
            hits = [x for x in candidates if matches(x["title"], keywords, exclude)]
            log(f"{name}: scanned {len(candidates)} items, {len(hits)} match(es)")
            for h in hits:
                jid = job_id(name, h["title"], h["link"])
                if jid not in seen:
                    seen[jid] = {"company": name, **h, "first_seen": datetime.now().isoformat()}
                    new_jobs.append({"company": name, **h})
        except Exception as e:
            log(f"{name}: ERROR — {e}")

    save_seen(seen)
    if new_jobs:
        notify(new_jobs, cfg)
    else:
        log("No new matching jobs this run.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Watch career pages for job openings.")
    ap.add_argument("--loop", action="store_true", help="Keep running and check on a schedule")
    ap.add_argument("--reset", action="store_true", help="Forget all previously seen jobs")
    args = ap.parse_args()

    if args.reset:
        SEEN_FILE.unlink(missing_ok=True)
        log("Seen-jobs history cleared.")
        return

    if args.loop:
        minutes = load_config().get("check_every_minutes", 60)
        log(f"Running every {minutes} minute(s). Press Ctrl+C to stop.")
        while True:
            run_check()
            time.sleep(minutes * 60)
    else:
        run_check()


if __name__ == "__main__":
    main()
