#!/usr/bin/env python3
"""Discover new first-party poll pages without silently promoting them into the model.

This stage is intentionally queue-only for sources that do not yet have a fully
validated automatic parser. It runs after reviewed enrichment so source-level
metadata can report both reviewed records and live discovery health.
"""
from __future__ import annotations

import copy
import json
import os
import re
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "pollster-registry.json"
FEED_PATH = ROOT / "data" / "polls.json"
CONFIG_PATH = ROOT / "config.json"
MAX_BYTES = 4_000_000


class DiscoveryError(ValueError):
    pass


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).replace("臺", "台")


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def registry_map(registry: dict) -> dict[str, dict]:
    pollsters = registry.get("pollsters")
    if registry.get("schema_version") != 1 or not isinstance(pollsters, list):
        raise DiscoveryError("Invalid pollster registry")
    ids = [p.get("pollster_id") for p in pollsters]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise DiscoveryError("Pollster registry ids are missing or duplicated")
    return {p["pollster_id"]: p for p in pollsters}


def discovery_pollsters(registry: dict) -> list[dict]:
    return [
        p for p in registry.get("pollsters", [])
        if p.get("discovery", {}).get("mode") == "html_index_queue"
    ]


def allowed_hosts(pollster: dict) -> set[str]:
    hosts = set()
    for url in pollster.get("discovery", {}).get("index_urls", []):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise DiscoveryError(f"Unsafe discovery index for {pollster.get('pollster_id')}")
        hosts.add(parsed.hostname)
    return hosts


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: set[str]):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self.hosts:
            raise DiscoveryError("Discovery redirect left first-party allowlist")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, hosts: set[str]) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts:
        raise DiscoveryError("Discovery URL outside first-party allowlist")
    error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "TaiwanElectionPollMonitor/1.1 (public-source research)",
                "Cache-Control": "no-cache",
            })
            with urllib.request.build_opener(SafeRedirect(hosts)).open(req, timeout=30) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise DiscoveryError("Discovery page exceeds download limit")
                return raw
        except (OSError, DiscoveryError) as exc:
            error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise error


def infer_county(title: str, matchups: dict) -> tuple[str | None, int]:
    text = compact(title)
    direct = [county for county in matchups if county in text]
    if len(direct) == 1:
        county = direct[0]
        hits = sum(1 for name in matchups[county] if compact(name) in text)
        return county, hits
    candidate_counties = []
    for county, candidates in matchups.items():
        hits = sum(1 for name in candidates if compact(name) in text)
        if hits:
            candidate_counties.append((county, hits))
    if len(candidate_counties) == 1:
        return candidate_counties[0]
    return None, 0


def discover_from_html(raw: bytes, index_url: str, pollster: dict, matchups: dict) -> list[dict]:
    try:
        doc = html.fromstring(raw)
    except Exception as exc:
        raise DiscoveryError("Discovery index is not parseable HTML") from exc
    cfg = pollster["discovery"]
    path_re = re.compile(cfg["article_path_pattern"])
    markers = [compact(x) for x in cfg.get("markers", [])]
    cues = [compact(x) for x in cfg.get("title_cues", ["支持", "領先", "選情", "膠著", "決勝", "對決"])]
    host = urlparse(index_url).hostname
    found = {}
    anchors = doc.xpath("//a[@href]")
    if not anchors:
        raise DiscoveryError("Discovery index structure changed: no links")
    for anchor in anchors:
        href = anchor.get("href", "")
        url = urljoin(index_url, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != host or not path_re.fullmatch(parsed.path):
            continue
        title = clean_title(anchor.text_content())
        ctitle = compact(title)
        if markers and not any(marker in ctitle for marker in markers):
            continue
        county, candidate_hits = infer_county(title, matchups)
        if not county:
            continue
        mayoral = any(x in ctitle for x in ("市長", "縣長"))
        support_cue = any(cue in ctitle for cue in cues)
        if not (candidate_hits >= 2 or (candidate_hits >= 1 and support_cue) or (mayoral and support_cue)):
            continue
        found[url] = {
            "pollster_id": pollster["pollster_id"],
            "source": pollster["source_label"],
            "publisher": pollster.get("publisher"),
            "title": title[:180],
            "county": county,
            "url": url,
        }
    return list(found.values())


def known_urls(feed: dict) -> set[str]:
    urls = set()
    for row in feed.get("records", []):
        if row.get("source_url"):
            urls.add(row["source_url"])
        urls.update(u for u in row.get("verification_urls", []) if u)
    return urls


def merge_discovery(feed: dict, registry: dict, config: dict, pages: dict[str, bytes], checked: str) -> dict:
    out = copy.deepcopy(feed)
    managed = {p["pollster_id"] for p in discovery_pollsters(registry)}
    preserved = [q for q in out.get("discovery_queue", []) if q.get("pollster_id") not in managed]
    known = known_urls(out)
    previous_urls = {q.get("url") for q in out.get("discovery_queue", []) if q.get("url")}
    new_queue = []
    failures = list(out.get("failures", []))
    source_by_name = {s.get("name"): s for s in out.get("sources", [])}
    history = list(out.get("history", []))

    for pollster in discovery_pollsters(registry):
        cfg = pollster["discovery"]
        entries = {}
        source_failures = []
        for index_url in cfg.get("index_urls", []):
            try:
                raw = pages[index_url]
                for entry in discover_from_html(raw, index_url, pollster, config.get("matchups", {})):
                    entries[entry["url"]] = entry
            except Exception as exc:
                source_failures.append({
                    "source": f"{pollster['source_label']} discovery",
                    "url": index_url,
                    "message": str(exc)[:180],
                })
        failures.extend(source_failures)
        pending = []
        for entry in entries.values():
            if entry["url"] in known:
                continue
            queued = {
                **entry,
                "status": "discovered_unverified",
                "reason": "一方站點自動發現；尚未通過完整訪期、樣本、方法、回應品質與候選人題目校驗，因此不入模。",
                "discovered_at": checked,
            }
            pending.append(queued)
            if entry["url"] not in previous_urls:
                history.insert(0, {
                    "date": checked,
                    "county": entry["county"],
                    "source_url": entry["url"],
                    "kind": "poll_source_discovered_unverified",
                })
        new_queue.extend(pending)
        source = source_by_name.get(pollster["source_label"])
        if source is None:
            source = {
                "name": pollster["source_label"],
                "url": cfg.get("index_urls", [""])[0],
                "validated_reports": 0,
                "reviewed_reports": 0,
                "status": "discovery_only",
            }
            out.setdefault("sources", []).append(source)
            source_by_name[pollster["source_label"]] = source
        source.update({
            "auto_discovery": True,
            "auto_discovery_status": "degraded" if source_failures else "checked",
            "auto_discovery_checked_at": checked,
            "auto_discovered": len(entries),
            "auto_known": sum(1 for e in entries.values() if e["url"] in known),
            "auto_pending": len(pending),
            "registry_pollster_id": pollster["pollster_id"],
        })
        source["note"] = (
            "一方站點已自動掃描；新頁面先進入待核驗佇列，完整方法學與回應品質校驗通過前不自動入模。"
            if not source_failures else
            "本輪一方站點自動發現受限；保留既有核驗資料，不把抓取失敗當成無新民調。"
        )

    out["discovery_queue"] = sorted(
        preserved + new_queue,
        key=lambda x: (x.get("county", ""), x.get("pollster_id", x.get("source", "")), x.get("title", "")),
    )
    out["failures"] = failures
    out["discovery_checked_at"] = checked
    out["pollster_registry"] = {
        "schema_version": registry.get("schema_version"),
        "updated_at": registry.get("updated_at"),
        "registered_pollsters": len(registry.get("pollsters", [])),
    }
    out["history"] = history[:100]
    if any(f.get("source", "").endswith(" discovery") for f in source_failures if isinstance(f, dict)):
        out["status"] = "degraded" if out.get("records") else "unavailable"
    addition = "山水與皮爾森一方索引已加入自動發現；新文章先列待核驗佇列，未通過完整校驗前不入模。"
    coverage = out.get("coverage_note", "").rstrip()
    if addition not in coverage:
        out["coverage_note"] = (coverage + (" " if coverage else "") + addition).strip()
    return out


def discover_live(feed: dict, registry: dict, config: dict, checked: str | None = None) -> dict:
    checked = checked or stamp()
    pages = {}
    for pollster in discovery_pollsters(registry):
        hosts = allowed_hosts(pollster)
        for index_url in pollster["discovery"].get("index_urls", []):
            try:
                pages[index_url] = fetch(index_url, hosts)
            except Exception as exc:
                pages[index_url] = b""
                # merge_discovery will convert this into a source-specific failure.
    return merge_discovery(feed, registry, config, pages, checked)


def main() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry_map(registry)
    feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    checked = stamp()
    pages = {}
    fetch_errors = {}
    for pollster in discovery_pollsters(registry):
        hosts = allowed_hosts(pollster)
        for index_url in pollster["discovery"].get("index_urls", []):
            try:
                pages[index_url] = fetch(index_url, hosts)
            except Exception as exc:
                fetch_errors[index_url] = str(exc)[:180]
                pages[index_url] = b""
    result = merge_discovery(feed, registry, config, pages, checked)
    if fetch_errors:
        failures = list(result.get("failures", []))
        known_failure_urls = {f.get("url") for f in failures}
        for pollster in discovery_pollsters(registry):
            for index_url in pollster["discovery"].get("index_urls", []):
                if index_url in fetch_errors and index_url not in known_failure_urls:
                    failures.append({
                        "source": f"{pollster['source_label']} discovery",
                        "url": index_url,
                        "message": fetch_errors[index_url],
                    })
        result["failures"] = failures
        result["status"] = "degraded" if result.get("records") else "unavailable"
    atomic_json(FEED_PATH, result)
    print(json.dumps({
        "registry_pollsters": result["pollster_registry"]["registered_pollsters"],
        "discovery_queue": len(result.get("discovery_queue", [])),
        "discovery_failures": len([f for f in result.get("failures", []) if str(f.get("source", "")).endswith(" discovery")]),
        "discovery_checked_at": result["discovery_checked_at"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
