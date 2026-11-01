"""Compare installed skills on disk with a Skill BOM (drift detection)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import Skill


@dataclass
class SkillDiff:
    name: str
    status: str  # ok | modified | not-in-bom | not-installed
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    installed_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"skill": self.name, "status": self.status}
        if self.installed_path:
            d["path"] = self.installed_path
        for k in ("added", "removed", "changed"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        return d


def _bom_skills(bom: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for c in bom.get("components", []):
        props = {p.get("name"): p.get("value") for p in c.get("properties", [])}
        if props.get("skillbom:kind") == "skill":
            out[c["name"]] = c
    return out


def _hash(c: dict[str, Any]) -> str | None:
    return next((h["content"] for h in c.get("hashes", []) if h.get("alg") == "SHA-256"), None)


def compare(installed: list[Skill], bom: dict[str, Any]) -> list[SkillDiff]:
    expected = _bom_skills(bom)
    diffs: list[SkillDiff] = []
    seen = set()
    for s in sorted(installed, key=lambda s: s.name):
        seen.add(s.name)
        comp = expected.get(s.name)
        if comp is None:
            diffs.append(SkillDiff(s.name, "not-in-bom", installed_path=s.rel_path))
            continue
        if _hash(comp) == s.digest:
            diffs.append(SkillDiff(s.name, "ok", installed_path=s.rel_path))
            continue
        want = {f["name"]: _hash(f) for f in comp.get("components", [])}
        have = {f.path: f.sha256 for f in s.files}
        diffs.append(SkillDiff(
            s.name, "modified",
            added=sorted(set(have) - set(want)),
            removed=sorted(set(want) - set(have)),
            changed=sorted(p for p in set(have) & set(want) if have[p] != want[p]),
            installed_path=s.rel_path,
        ))
    for name in sorted(set(expected) - seen):
        diffs.append(SkillDiff(name, "not-installed"))
    return diffs
