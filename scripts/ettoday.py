"""ETtoday Poll Cloud adapter.

The adapter separates discovery from admission. Discovery uses the publisher RSS
feed only to locate ETtoday article URLs. Parsing fails closed unless the article
contains a complete mayoral matchup plus fieldwork and sampling metadata.
Reviewed seed records remain available when the live feed or article is
temporarily unavailable.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urlparse

from lxml import etree, html

SOURCE = "ETtoday 民調雲"
POLLSTER_ID = "ettoday"
PUBLISHER = "ETtoday 新聞雲"
INDEX = "https://feeds.feedburner.com/ettoday/newslist"
HOSTS = {
    "ettoday.net",
    "www.ettoday.net",
    "feeds.feedburner.com",
    "feedproxy.google.com",
}
VERSION = 1
COUNTIES = [
    "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市",
    "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "屏東縣",
    "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
]


class InvalidETtodayReport(ValueError):
    pass


def canonical(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).replace("臺", "台").replace("啓", "啟")


def canonical_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in {"ettoday.net", "www.ettoday.net"} or p.username or p.password:
        raise InvalidETtodayReport("Not an ETtoday publisher URL")
    return f"https://www.ettoday.net{p.path}" + (f"?{p.query}" if p.query else "")


def discover(raw: bytes):
    """Return mayoral-poll ETtoday article entries from the publisher RSS feed."""
    try:
        doc = etree.fromstring(raw, parser=etree.XMLParser(recover=True))
    except Exception as exc:
        raise InvalidETtodayReport("ETtoday feed is not parseable XML") from exc
    items = doc.xpath("//*[local-name()='item']")
    if not items:
        raise InvalidETtodayReport("ETtoday feed structure changed: no items")
    found = {}
    for item in items:
        title = "".join(item.xpath("./*[local-name()='title']/text()"))
        desc = "".join(item.xpath("./*[local-name()='description']/text()"))
        context = canonical(title + " " + desc)
        if "民調" not in context or not any(x in context for x in ("市長", "縣長")):
            continue
        county = next((c for c in COUNTIES if c in context), None)
        if not county:
            continue
        urls = []
        for tag in ("link", "guid"):
            urls.extend(item.xpath(f"./*[local-name()='{tag}']/text()"))
        publisher_url = None
        for value in urls:
            try:
                publisher_url = canonical_url(value.strip())
                break
            except (InvalidETtodayReport, AttributeError):
                continue
        if not publisher_url:
            continue
        found[publisher_url] = {"url": publisher_url, "title": title.strip()[:160], "county": county}
    return list(found.values())[:20]


def article_text(raw: bytes) -> str:
    try:
        doc = html.fromstring(raw)
    except Exception as exc:
        raise InvalidETtodayReport("ETtoday article is not parseable HTML") from exc
    text = unicodedata.normalize("NFKC", doc.text_content())
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    if len(text) < 400:
        raise InvalidETtodayReport("ETtoday article text is unexpectedly short")
    return text


def _date_range(text: str):
    patterns = [
        r"(?:調查辦理時間|調查時間)(?:為|：|:)?\s*(20\d{2})年(\d{1,2})月(\d{1,2})日至(?:(\d{1,2})月)?(\d{1,2})日",
        r"調查於\s*(20\d{2})年(\d{1,2})月(\d{1,2})日至(?:(\d{1,2})月)?(\d{1,2})日進行",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            y, mo, d, end_mo, end_d = m.groups()
            return date(int(y), int(mo), int(d)).isoformat(), date(int(y), int(end_mo or mo), int(end_d)).isoformat()
    raise InvalidETtodayReport("Missing ETtoday fieldwork dates")


def _number(patterns, text, cast=float):
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return cast(m.group(1).replace(",", ""))
    return None


def _support_fragment(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    anchor = compact.find("若明天")
    if anchor < 0:
        anchor = compact.find("市長選舉支持度")
    if anchor < 0:
        raise InvalidETtodayReport("Cannot locate ETtoday vote-intention question")
    fragment = compact[anchor:anchor + 520]
    for stop in ("看好度", "投票意願", "施政滿意", "市政能力"):
        i = fragment.find(stop)
        if i > 80:
            fragment = fragment[:i]
    return fragment


def parse(raw: bytes, entry: dict, today: date, expected_matchups: dict):
    text = article_text(raw)
    context = canonical(entry.get("title", "") + text[:1800])
    counties = [c for c in COUNTIES if c in context]
    county = entry.get("county") if entry.get("county") in counties else (counties[0] if len(counties) == 1 else None)
    if not county or county not in expected_matchups:
        raise InvalidETtodayReport("County or configured matchup is unavailable")
    expected = expected_matchups[county]
    start, end = _date_range(text)
    if not (date(2025, 1, 1) <= date.fromisoformat(start) <= date.fromisoformat(end) <= today):
        raise InvalidETtodayReport("Invalid or future ETtoday fieldwork dates")
    sample_n = _number([
        r"回收有效樣本(?:數)?\s*([\d,]+)\s*份",
        r"有效樣本(?:數)?(?:為|共)?\s*([\d,]+)\s*份",
    ], text, int)
    moe = _number([r"抽樣誤差(?:為|是|:|：)?\s*[±正負]?\s*(\d+(?:\.\d+)?)\s*%", r"誤差為\s*[±正負]?\s*(\d+(?:\.\d+)?)"], text)
    population_size = _number([r"母體(?:人)?數(?:為|:|：)?[^\d]{0,20}([\d,]+)"], text, int)
    if not sample_n or not 100 <= sample_n <= 100000 or not moe or not 0 < moe < 15:
        raise InvalidETtodayReport("Missing or implausible ETtoday sampling metadata")
    if "封閉式網路問卷" not in text or not ("EDM" in text and "手機簡訊" in text):
        raise InvalidETtodayReport("Unsupported ETtoday survey mode")
    fragment = _support_fragment(text)
    candidates = []
    for name, bloc in expected.items():
        m = re.search(re.escape(canonical(name)) + r".{0,30}?(\d+(?:\.\d+)?)%", fragment)
        if not m:
            raise InvalidETtodayReport(f"Configured candidate missing from ETtoday vote question: {name}")
        candidates.append({"name": name, "support": float(m.group(1)), "bloc": bloc})
    undecided = _number([
        r"另有\s*(\d+(?:\.\d+)?)%[^。]{0,50}(?:尚未決定|不知道|沒有意見|未表態)",
        r"(\d+(?:\.\d+)?)%[^。]{0,30}(?:尚未決定|未表態)",
    ], fragment)
    if undecided is None:
        raise InvalidETtodayReport("Missing ETtoday undecided share")
    total = sum(c["support"] for c in candidates) + undecided
    if abs(total - 100) > 2:
        raise InvalidETtodayReport("ETtoday vote-intention percentages do not sum to 100")
    funding = "東森民調雲股份有限公司" if "東森民調雲股份有限公司" in text else SOURCE
    identity = "|".join([POLLSTER_ID, county, start, end, ",".join(sorted(expected))])
    return [{
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "county": county,
        "source": SOURCE,
        "pollster_id": POLLSTER_ID,
        "publisher": PUBLISHER,
        "source_url": canonical_url(entry["url"]),
        "report_title": entry.get("title") or f"{county}長選舉民調",
        "field_start": start,
        "date": end,
        "published_at": None,
        "sample_n": sample_n,
        "population": f"設籍{county}且年滿20歲以上民眾",
        "population_size": population_size,
        "method": "EDM及手機簡訊邀請；封閉式網路問卷；分層比例抽樣；raking加權",
        "method_class": "closed_online_panel",
        "sampling_frame": "ETtoday民調雲自建會員資料庫",
        "weighting": "raking_ratio_estimation",
        "margin_of_error": float(moe),
        "confidence_level": 95,
        "funding": funding,
        "supervisor": "謝惠玲" if "謝惠玲" in text else None,
        "sample_note": "公布之加權全體有效樣本；封閉式會員網路樣本",
        "multiple_matchups": False,
        "question_number": 1,
        "candidates": candidates,
        "undecided": float(undecided),
        "nonvote": 0.0,
        "verification_status": "automatic_original_article",
    }]


def reviewed_record(entry: dict, today: date):
    required = ["county", "field_start", "date", "sample_n", "supports", "names", "blocs", "undecided", "verification_urls"]
    if any(k not in entry for k in required):
        raise InvalidETtodayReport("Reviewed ETtoday record missing required fields")
    start, end = date.fromisoformat(entry["field_start"]), date.fromisoformat(entry["date"])
    if not (date(2025, 1, 1) <= start <= end <= today):
        raise InvalidETtodayReport("Reviewed ETtoday dates invalid")
    if not (len(entry["names"]) == len(entry["supports"]) == len(entry["blocs"]) >= 2):
        raise InvalidETtodayReport("Reviewed ETtoday candidate vectors invalid")
    candidates = [
        {"name": n, "support": float(v), "bloc": b}
        for n, v, b in zip(entry["names"], entry["supports"], entry["blocs"])
    ]
    total = sum(c["support"] for c in candidates) + float(entry["undecided"]) + float(entry.get("nonvote", 0))
    if abs(total - 100) > 2:
        raise InvalidETtodayReport("Reviewed ETtoday percentages do not sum to 100")
    identity = "|".join([POLLSTER_ID, entry["county"], entry["field_start"], entry["date"], ",".join(sorted(entry["names"]))])
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "county": entry["county"],
        "source": SOURCE,
        "pollster_id": POLLSTER_ID,
        "publisher": PUBLISHER,
        "source_url": entry["verification_urls"][0],
        "original_publisher_url": entry.get("original_publisher_url", "https://www.ettoday.net/"),
        "verification_urls": entry["verification_urls"],
        "report_title": entry["title"],
        "field_start": entry["field_start"],
        "date": entry["date"],
        "published_at": entry.get("published_at"),
        "sample_n": int(entry["sample_n"]),
        "population": entry.get("population", f"設籍{entry['county']}且年滿20歲以上民眾"),
        "population_size": entry.get("population_size"),
        "method": entry["method"],
        "method_class": "closed_online_panel",
        "sampling_frame": entry.get("sampling_frame", "ETtoday民調雲自建會員資料庫"),
        "weighting": entry.get("weighting", "raking_ratio_estimation"),
        "margin_of_error": float(entry["margin_of_error"]),
        "confidence_level": 95,
        "funding": entry.get("funding", "東森民調雲股份有限公司"),
        "supervisor": entry.get("supervisor", "謝惠玲"),
        "sample_note": "公布之加權全體有效樣本；封閉式會員網路樣本",
        "multiple_matchups": bool(entry.get("multiple_matchups", False)),
        "question_number": int(entry.get("question_number", 1)),
        "candidates": candidates,
        "undecided": float(entry["undecided"]),
        "nonvote": float(entry.get("nonvote", 0)),
        "verification_status": "reviewed_multi_source_methodology",
        "ingestion": "reviewed_pollster_facts",
    }
