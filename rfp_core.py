from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dotenv import load_dotenv

load_dotenv(override=False)

DB_PATH = os.getenv("DB_PATH", "grant_tracker.sqlite3")
GRANTS_GOV_SEARCH2_URL = "https://api.grants.gov/v1/api/search2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    funder TEXT,
    url TEXT,
    opening_date TEXT,
    closing_date TEXT,
    status TEXT,
    award_amount TEXT,
    match_required TEXT,
    eligibility TEXT,
    fit_score INTEGER DEFAULT 0,
    fit_reason TEXT,
    summary TEXT,
    stage TEXT DEFAULT 'New',
    owner TEXT,
    project_idea TEXT,
    notes TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    content_hash TEXT,
    is_archived INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    source TEXT NOT NULL,
    found_count INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    notes TEXT
);
"""

GRANTS_GOV_KEYWORDS = [
    "wetland", "waterfowl", "wildlife habitat", "migratory birds", "water quality agriculture",
    "working lands conservation", "bottomland hardwood", "Lower Mississippi", "Arkansas conservation",
    "soil health water quality", "environmental education wetlands", "NSF ecology", "USDA natural resources",
    "EPA farmer", "NAWCA", "rural conservation", "floodplain restoration", "habitat restoration",
]

MONITORED_PAGES = [
    "https://www.nfwf.org/apply-grant",
    "https://www.nfwf.org/programs/lower-mississippi-alluvial-valley-restoration-fund",
    "https://www.nfwf.org/programs/conservation-partners-program",
    "https://www.fws.gov/service/north-american-wetlands-conservation-act-nawca-us-small-grants",
    "https://www.fws.gov/program/partners-fish-and-wildlife",
    "https://www.epa.gov/gulfofamerica",
    "https://www.epa.gov/gulfofamerica/working-farmers-innovative-and-economic-solutions",
    "https://www.nifa.usda.gov/grants/funding-opportunities",
    "https://southern.sare.org/grants/",
    "https://www.nsf.gov/funding",
    "https://www.fishwildlife.org/afwa-informs/multi-state-conservation-grants-program",
    "https://www.waltonfamilyfoundation.org/grants",
    "https://www.waltonfamilyfoundation.org/grants/grant-proposals",
    "https://www.dorisduke.org/grants/",
    "https://www.usendowment.org/funding-opportunities/",
    "https://www.arcf.org/apply/",
    "https://www.arkansasee.org/grants",
    "https://conservationalliance.com/grants/",
    "https://www.weyerhaeuser.com/sustainability/communities/giving-fund/",
]

POSITIVE_TERMS = {
    "wetland": 8, "wetlands": 8, "waterfowl": 10, "mallard": 8, "duck": 6,
    "migratory bird": 7, "wildlife habitat": 8, "nawca": 10, "nfwf": 8, "usfws": 7,
    "epa": 6, "usda": 5, "nrcs": 6, "nsf": 5, "conservation": 5, "restoration": 7,
    "enhancement": 5, "hydrology": 7, "floodplain": 6, "bottomland hardwood": 9, "oak": 5,
    "working lands": 8, "rice": 5, "agriculture": 5, "water quality": 8, "nutrient": 5,
    "sediment": 5, "soil health": 6, "set-aside": 8, "producer": 5, "private lands": 6,
    "education": 4, "workforce": 5, "research": 5, "demonstration": 6, "arkansas": 8,
    "lower mississippi": 10, "lmav": 10, "bayou meto": 8, "cache river": 8, "white river": 7,
    "delta": 5, "forest": 4, "forestry": 4, "climate resilience": 5,
}

NEGATIVE_TERMS = ["medical", "health care", "cybersecurity", "space", "astronomy", "ocean", "coral", "marine debris", "opioid", "vaccine"]

STAGES = ["New", "Review", "Good Fit", "Maybe", "Not a Fit", "Concepting", "Writing", "Submitted", "Awarded", "Declined", "Watch Next Cycle"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_date(text: str) -> str:
    if not text:
        return ""
    try:
        return date_parser.parse(str(text), fuzzy=True).date().isoformat()
    except Exception:
        return ""


def extract_dates(text: str) -> Tuple[str, str]:
    opening = ""
    closing = ""
    due_patterns = [
        r"(?:due date|deadline|proposal due|applications? due|submission deadline|full proposal deadline)[^\n:;]{0,60}[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})[^\n]{0,70}(?:deadline|due|applications? close)",
        r"(?:due date|deadline|applications? due|proposal due)[^\n:;]{0,60}[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})[^\n]{0,70}(?:deadline|due)",
    ]
    open_patterns = [
        r"(?:posted|published|release date|rfp released|opens?)[^\n:;]{0,60}[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"(?:posted|published|release date|rfp released|opens?)[^\n:;]{0,60}[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pat in due_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            closing = parse_date(m.group(1))
            break
    for pat in open_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            opening = parse_date(m.group(1))
            break
    return opening, closing


def score(text: str) -> Tuple[int, str]:
    hay = text.lower()
    score_value = 0
    matches = []
    for term, points in POSITIVE_TERMS.items():
        if term in hay:
            score_value += points
            matches.append(term)
    for term in NEGATIVE_TERMS:
        if term in hay:
            score_value -= 15
            matches.append(f"exclude:{term}")
    return max(0, min(100, score_value)), ", ".join(sorted(set(matches))[:22])


def project_idea(title: str, summary: str, reason: str) -> str:
    text = f"{title} {summary} {reason}".lower()
    ideas = []
    if any(x in text for x in ["wetland", "waterfowl", "migratory bird", "nawca"]):
        ideas.append("Wetland and waterfowl habitat enhancement")
    if any(x in text for x in ["water quality", "nutrient", "sediment", "soil health", "farmer", "producer", "working lands"]):
        ideas.append("Working-lands water quality and wildlife habitat demonstration")
    if any(x in text for x in ["research", "nsf", "ecology"]):
        ideas.append("University-led wetland/waterfowl ecology research")
    if any(x in text for x in ["education", "workforce", "training", "student"]):
        ideas.append("Wetland education and conservation workforce training")
    if any(x in text for x in ["forest", "bottomland", "oak", "hardwood"]):
        ideas.append("Bottomland hardwood restoration or oak regeneration research")
    return "; ".join(ideas) if ideas else "Review for a Five Oaks conservation, research, or education concept."


def upsert(opp: Dict[str, str]) -> bool:
    conn = db()
    existing = conn.execute("SELECT id FROM opportunities WHERE external_id=?", (opp["external_id"],)).fetchone()
    ts = now()
    if existing:
        conn.execute(
            """
            UPDATE opportunities SET source=?, title=?, funder=?, url=?, opening_date=?, closing_date=?, status=?,
                award_amount=?, match_required=?, eligibility=?, fit_score=?, fit_reason=?, summary=?,
                last_seen=?, content_hash=?
            WHERE external_id=?
            """,
            (
                opp.get("source", ""), opp.get("title", ""), opp.get("funder", ""), opp.get("url", ""),
                opp.get("opening_date", ""), opp.get("closing_date", ""), opp.get("status", ""),
                opp.get("award_amount", ""), opp.get("match_required", ""), opp.get("eligibility", ""),
                int(opp.get("fit_score", 0) or 0), opp.get("fit_reason", ""), opp.get("summary", ""),
                ts, opp.get("content_hash", ""), opp["external_id"],
            ),
        )
        conn.commit()
        return False
    conn.execute(
        """
        INSERT INTO opportunities
        (external_id, source, title, funder, url, opening_date, closing_date, status, award_amount,
         match_required, eligibility, fit_score, fit_reason, summary, stage, owner, project_idea, notes,
         first_seen, last_seen, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            opp["external_id"], opp.get("source", ""), opp.get("title", ""), opp.get("funder", ""),
            opp.get("url", ""), opp.get("opening_date", ""), opp.get("closing_date", ""), opp.get("status", ""),
            opp.get("award_amount", ""), opp.get("match_required", ""), opp.get("eligibility", ""),
            int(opp.get("fit_score", 0) or 0), opp.get("fit_reason", ""), opp.get("summary", ""),
            "New", "", opp.get("project_idea", ""), "", ts, ts, opp.get("content_hash", ""),
        ),
    )
    conn.commit()
    return True


def log_scan(source: str, found: int, new: int, notes: str = "") -> None:
    conn = db()
    conn.execute("INSERT INTO scan_log (run_at, source, found_count, new_count, notes) VALUES (?, ?, ?, ?, ?)", (now(), source, found, new, notes))
    conn.commit()


def grants_gov_search() -> List[Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    for keyword in GRANTS_GOV_KEYWORDS:
        payload = {"rows": 30, "keyword": keyword, "eligibilities": "", "agencies": "", "oppStatuses": "forecasted|posted", "aln": "", "fundingCategories": ""}
        try:
            r = requests.post(GRANTS_GOV_SEARCH2_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            r.raise_for_status()
            hits = (r.json().get("data", {}) or {}).get("oppHits", []) or []
        except Exception as e:
            continue
        for hit in hits:
            oid = str(hit.get("id") or hit.get("number") or hit.get("title"))
            title = hit.get("title") or "Untitled opportunity"
            funder = hit.get("agencyName") or hit.get("agencyCode") or ""
            summary = f"Matched Grants.gov keyword: {keyword}"
            raw = str(hit)
            fit, reason = score(f"{title} {funder} {summary} {raw}")
            rows[oid] = {
                "external_id": f"grantsgov::{oid}",
                "source": "Grants.gov",
                "title": title,
                "funder": funder,
                "url": f"https://www.grants.gov/search-results-detail/{oid}",
                "opening_date": parse_date(hit.get("openDate", "")),
                "closing_date": parse_date(hit.get("closeDate", "")),
                "status": hit.get("oppStatus", ""),
                "award_amount": "",
                "match_required": "Review RFP",
                "eligibility": "Review RFP",
                "fit_score": fit,
                "fit_reason": reason,
                "summary": summary,
                "project_idea": project_idea(title, summary, reason),
                "content_hash": hash_text(raw),
            }
    return list(rows.values())


def page_monitor_search() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for url in MONITORED_PAGES:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Five Oaks Grant Tracker/1.0"})
            r.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else url
        text = soup.get_text("\n", strip=True)
        opening, closing = extract_dates(text[:15000])
        links = []
        for a in soup.find_all("a", href=True):
            label = clean(a.get_text(" ", strip=True))
            href = a["href"]
            combined = f"{label} {href}".lower()
            if any(x in combined for x in ["rfp", "grant", "funding", "proposal", "nofo", "apply", "application", "loi", "letter of inquiry", "open call"]):
                links.append(label)
        summary = "; ".join(links[:12]) if links else clean(text[:900])
        fit, reason = score(f"{title} {url} {summary} {text[:7000]}")
        rows.append({
            "external_id": f"page::{hash_text(url)}",
            "source": "RFP Page Monitor",
            "title": title,
            "funder": url.split("/")[2] if "://" in url else "",
            "url": url,
            "opening_date": opening,
            "closing_date": closing,
            "status": "Monitored",
            "award_amount": "",
            "match_required": "Review",
            "eligibility": "Review",
            "fit_score": fit,
            "fit_reason": reason,
            "summary": summary,
            "project_idea": project_idea(title, summary, reason),
            "content_hash": hash_text(text[:120000]),
        })
    return rows


def run_scan() -> List[Dict[str, str]]:
    all_new: List[Dict[str, str]] = []
    for source_name, func in [("Grants.gov", grants_gov_search), ("RFP Page Monitor", page_monitor_search)]:
        try:
            found = func()
            new_count = 0
            for opp in found:
                is_new = upsert(opp)
                if is_new:
                    new_count += 1
                    all_new.append(opp)
            log_scan(source_name, len(found), new_count)
        except Exception as e:
            log_scan(source_name, 0, 0, f"ERROR: {e}")
    return all_new


def list_opportunities(include_archived: bool = False) -> List[Dict[str, str]]:
    conn = db()
    where = "" if include_archived else "WHERE is_archived=0"
    rows = conn.execute(f"SELECT * FROM opportunities {where} ORDER BY fit_score DESC, closing_date ASC, first_seen DESC").fetchall()
    return [dict(r) for r in rows]


def update_opportunities(records: List[Dict]) -> None:
    conn = db()
    allowed = ["stage", "owner", "project_idea", "notes", "award_amount", "match_required", "eligibility", "is_archived"]
    for rec in records:
        oid = rec.get("id")
        if not oid:
            continue
        sets, vals = [], []
        for col in allowed:
            if col in rec:
                sets.append(f"{col}=?")
                vals.append(rec[col])
        if sets:
            vals.append(oid)
            conn.execute(f"UPDATE opportunities SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()


def scan_log_rows() -> List[Dict]:
    conn = db()
    rows = conn.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


def send_alert(new_rows: List[Dict[str, str]]) -> bool:
    host = os.getenv("SMTP_HOST", "")
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    alert_to = os.getenv("ALERT_TO", "")
    alert_from = os.getenv("ALERT_FROM", username)
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    min_score = int(os.getenv("MIN_ALERT_SCORE", "60") or 60)
    if not all([host, username, password, alert_to, alert_from]):
        return False
    filtered = [r for r in new_rows if int(r.get("fit_score", 0) or 0) >= min_score]
    if not filtered:
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Five Oaks Grant Tracker: {len(filtered)} new high-fit RFPs"
    msg["From"] = alert_from
    msg["To"] = alert_to
    html = ["<h2>New high-fit funding opportunities</h2>", "<ol>"]
    for r in filtered:
        html.append(f"<li><b>{r.get('title','')}</b><br>Funder: {r.get('funder','')}<br>Deadline: {r.get('closing_date') or 'Not detected'}<br>Fit: {r.get('fit_score')}<br>Idea: {r.get('project_idea','')}<br><a href='{r.get('url','')}'>Open RFP</a></li><br>")
    html.append("</ol>")
    msg.attach(MIMEText("\n".join(html), "html"))
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(alert_from, [alert_to], msg.as_string())
    return True


def run_daily() -> Dict[str, object]:
    new_rows = run_scan()
    email_sent = send_alert(new_rows)
    return {"new_count": len(new_rows), "email_sent": email_sent}
