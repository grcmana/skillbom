"""Policy checks over a Skill BOM. Deterministic; no network, no LLM."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import PROFILE_VERSION

DEFAULT_POLICY: dict[str, Any] = {
    "rules": {
        "bom-profile": {"severity": "error"},
        "skill-version": {"severity": "error"},
        "skill-semver": {"severity": "warn"},
        "skill-hash": {"severity": "error"},
        "skill-license": {"severity": "error"},
        "skill-name-matches-folder": {"severity": "error"},
        "required-metadata": {"severity": "error", "keys": ["author"]},
        "knowledge-freshness": {"severity": "warn", "max_age_days": 183, "require_as_of": False},
    }
}

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SEVERITIES = ("error", "warn", "off")


@dataclass
class Finding:
    rule: str
    severity: str
    target: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "severity": self.severity, "target": self.target, "message": self.message}


def load_policy(path: Path | None) -> dict[str, Any]:
    policy = copy.deepcopy(DEFAULT_POLICY)
    if path is None:
        return policy
    user = json.loads(path.read_text(encoding="utf-8"))
    for name, cfg in (user.get("rules") or {}).items():
        if name not in policy["rules"]:
            raise ValueError(f"unknown rule in policy: {name}")
        if not isinstance(cfg, dict):
            raise ValueError(f"rule {name} must be an object")
        sev = cfg.get("severity", policy["rules"][name]["severity"])
        if sev not in SEVERITIES:
            raise ValueError(f"rule {name}: severity must be one of {SEVERITIES}")
        policy["rules"][name].update(cfg)
    return policy


def _props(c: dict[str, Any]) -> dict[str, str]:
    return {p["name"]: p.get("value", "") for p in c.get("properties", []) if "name" in p}


def _sha256(c: dict[str, Any]) -> str | None:
    for h in c.get("hashes", []):
        if h.get("alg") == "SHA-256":
            return h.get("content")
    return None


def run(bom: dict[str, Any], policy: dict[str, Any], today: date) -> list[Finding]:
    rules = policy["rules"]
    findings: list[Finding] = []

    def add(rule: str, target: str, message: str) -> None:
        sev = rules[rule]["severity"]
        if sev != "off":
            findings.append(Finding(rule, sev, target, message))

    meta_props = _props(bom.get("metadata", {}))
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.6":
        add("bom-profile", "bom", "expected a CycloneDX 1.6 BOM")
    if meta_props.get("skillbom:profile") != PROFILE_VERSION:
        add("bom-profile", "bom",
            f"expected skillbom:profile {PROFILE_VERSION}, found {meta_props.get('skillbom:profile', 'none')}")

    components = bom.get("components", [])
    skills = [c for c in components if _props(c).get("skillbom:kind") == "skill"]
    knowledge = [c for c in components if _props(c).get("skillbom:kind") == "knowledge"]
    if not skills:
        add("bom-profile", "bom", "no skill components found")

    for c in skills:
        name = c.get("name", "?")
        target = f"skill:{name}"
        props = _props(c)
        version = c.get("version")
        if not version:
            add("skill-version", target, "no version declared (metadata.version in SKILL.md)")
        elif not SEMVER.match(version):
            add("skill-semver", target, f"version '{version}' is not semantic versioning (MAJOR.MINOR.PATCH)")
        digest = _sha256(c)
        if not digest or not SHA256.match(digest):
            add("skill-hash", target, "missing or malformed SHA-256 content hash")
        for f in c.get("components", []):
            fd = _sha256(f)
            if not fd or not SHA256.match(fd):
                add("skill-hash", target, f"file '{f.get('name')}' has no valid SHA-256 hash")
        if not c.get("licenses"):
            add("skill-license", target, "no licence declared (license in SKILL.md)")
        folder = props.get("skillbom:path", "").rstrip("/").rsplit("/", 1)[-1]
        if folder and folder != "." and folder != name:
            add("skill-name-matches-folder", target, f"name '{name}' does not match folder '{folder}'")
        authors = [a.get("name") for a in c.get("authors", []) if a.get("name")]
        for key in rules["required-metadata"].get("keys", []):
            present = bool(authors) if key == "author" else f"skillbom:meta:{key}" in props
            if not present:
                add("required-metadata", target, f"metadata.{key} is missing")

    fresh = rules["knowledge-freshness"]
    max_age = int(fresh.get("max_age_days", 183))
    for k in knowledge:
        props = _props(k)
        target = k.get("bom-ref", k.get("name", "?"))
        as_of = props.get("skillbom:as-of")
        if not as_of:
            if fresh.get("require_as_of"):
                add("knowledge-freshness", target, "no as_of date declared")
            continue
        try:
            d = date.fromisoformat(as_of[:10])
        except ValueError:
            add("knowledge-freshness", target, f"as_of '{as_of}' is not an ISO date")
            continue
        age = (today - d).days
        if age > max_age:
            add("knowledge-freshness", target, f"as_of {as_of} is {age} days old (limit {max_age})")
        elif age < 0:
            add("knowledge-freshness", target, f"as_of {as_of} is in the future")
    return findings
