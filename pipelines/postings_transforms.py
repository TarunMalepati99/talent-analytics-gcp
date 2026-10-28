"""Pure transform functions for the postings normalizer.

Kept free of Beam imports so they can be unit-tested directly (tests/test_postings_transforms.py)
and reused by the Beam pipeline in normalize_postings.py.

Greenhouse and Lever describe the same thing (an open requisition) with
different shapes, field names and timestamp formats. This module maps both
onto one schema and adds two derived fields recruiting analytics needs:
`role_family` and `seniority`.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

NORMALIZED_FIELDS = [
    "posting_key", "source", "board", "source_job_id", "title", "department", "team",
    "location", "workplace_type", "is_remote", "role_family", "seniority",
    "posted_at", "updated_at", "url", "ingested_at",
]

# Order matters: the first matching family wins, so more specific patterns come first.
_EXACT = {"ai", "ml", "hr", "hrbp", "ux", "ui", "vp", "sre", "bdr", "sdr", "ops", "r&d"}


def _words(*alternatives: str) -> re.Pattern:
    """Case-insensitive whole-word match. Stems may take a suffix (recruit -> recruiter);
    short acronyms must match exactly so 'ai' never matches inside 'aircraft'."""
    stems = [a for a in alternatives if a not in _EXACT]
    exact = [re.escape(a) for a in alternatives if a in _EXACT]
    parts = []
    if stems:
        parts.append(r"\b(?:" + "|".join(stems) + r")\w*")
    if exact:
        parts.append(r"(?<!\w)(?:" + "|".join(exact) + r")(?!\w)")
    return re.compile("|".join(parts), re.I)


ROLE_FAMILY_RULES: list[tuple[str, re.Pattern]] = [
    ("people_hr", _words("recruit", "talent", "people", "hr", "hrbp", "human resources", "compensation", "benefits")),
    ("data_ml", _words("data", "machine learning", "ml", "ai", "analytic", "analyst", "scientist", "statistic")),
    ("research", _words("research", "r&d", "laborator", "lab tech")),
    ("engineering", _words("engineer", "developer", "sre", "devops", "software", "infrastructure", "security", "architect")),
    ("sales", _words("sales", "account executive", "account manager", "business development", "bdr", "sdr", "partnership")),
    ("product_design", _words("product", "design", "ux", "ui")),
    ("operations", _words("operation", "ops", "supply", "logistic", "manufactur", "program manager")),
    ("go_to_market", _words("marketing", "customer success", "support", "solution")),
    ("finance_legal", _words("financ", "accounting", "legal", "counsel", "tax", "audit")),
    ("management", _words("manager", "director", "head of", "vp", "vice president", "chief")),
]

SENIORITY_RULES: list[tuple[str, re.Pattern]] = [
    ("intern", re.compile(r"\bintern(ship)?\b", re.I)),
    ("entry", re.compile(r"\b(new grad|graduate|junior|jr\.?|entry|associate|early career|university)\b", re.I)),
    ("executive", re.compile(r"\b(vp|vice president|chief|head of|cto|cfo|ceo)\b", re.I)),
    ("manager", re.compile(r"\b(manager|director)\b", re.I)),
    ("staff_plus", re.compile(r"\b(staff|principal|distinguished|fellow|lead)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b|\bIII\b", re.I)),
]


def classify(title: str, rules: list[tuple[str, re.Pattern]], default: str) -> str:
    for label, pattern in rules:
        if pattern.search(title or ""):
            return label
    return default


def posting_key(source: str, board: str, job_id: str) -> str:
    return hashlib.sha1(f"{source}|{board}|{job_id}".encode()).hexdigest()


def _iso_to_utc(value: str | None) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _epoch_ms_to_utc(value: int | None) -> str | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _remote_flag(workplace_type: str | None, location: str | None) -> bool:
    text = f"{workplace_type or ''} {location or ''}".lower()
    return "remote" in text


def normalize_greenhouse(job: dict) -> dict:
    location = (job.get("location") or {}).get("name")
    depts = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
    workplace = "remote" if _remote_flag(None, location) else None
    return {
        "department": depts[0] if depts else None,
        "team": depts[-1] if len(depts) > 1 else None,
        "title": (job.get("title") or "").strip(),
        "location": location,
        "workplace_type": workplace,
        "posted_at": _iso_to_utc(job.get("first_published") or job.get("updated_at")),
        "updated_at": _iso_to_utc(job.get("updated_at")),
        "url": job.get("absolute_url"),
    }


def normalize_lever(job: dict) -> dict:
    cats = job.get("categories") or {}
    return {
        "department": cats.get("department"),
        "team": cats.get("team"),
        "title": (job.get("text") or "").strip(),
        "location": cats.get("location"),
        "workplace_type": (job.get("workplaceType") or None),
        "posted_at": _epoch_ms_to_utc(job.get("createdAt")),
        "updated_at": _epoch_ms_to_utc(job.get("updatedAt") or job.get("createdAt")),
        "url": job.get("hostedUrl"),
    }


NORMALIZERS = {"greenhouse": normalize_greenhouse, "lever": normalize_lever}


def normalize_record(raw: dict) -> dict:
    """Map one raw landing record (see ingestion/fetch_postings.py) to the normalized schema.

    Raises ValueError for records that cannot be normalized; the pipeline routes
    those to a dead-letter output instead of failing the job.
    """
    source = raw.get("source")
    if source not in NORMALIZERS:
        raise ValueError(f"unknown source: {source!r}")
    payload = raw["payload"]
    job = json.loads(payload) if isinstance(payload, str) else payload
    fields = NORMALIZERS[source](job)
    if not fields["title"]:
        raise ValueError("posting has no title")

    classify_text = f"{fields['title']} {fields['department'] or ''}"
    out = {
        "posting_key": posting_key(source, raw["board"], raw["source_job_id"]),
        "source": source,
        "board": raw["board"],
        "source_job_id": raw["source_job_id"],
        **fields,
        "is_remote": _remote_flag(fields["workplace_type"], fields["location"]),
        # Title alone decides role family; department text is a fallback only.
        "role_family": classify(fields["title"], ROLE_FAMILY_RULES, "")
        or classify(classify_text, ROLE_FAMILY_RULES, "other"),
        "seniority": classify(fields["title"], SENIORITY_RULES, "mid"),
        "ingested_at": raw["ingested_at"],
    }
    return {k: out.get(k) for k in NORMALIZED_FIELDS}


def latest(records: list[dict]) -> dict:
    """Dedup rule: same posting seen in several loads -> keep the most recent ingest."""
    return max(records, key=lambda r: (r.get("ingested_at") or "", r.get("updated_at") or ""))
