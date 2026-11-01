"""Build a CycloneDX 1.6 BOM following the Skill BOM profile (see SPEC.md)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import PROFILE_VERSION, __version__
from .model import Knowledge, Skill

SPEC_VERSION = "1.6"
NS = "skillbom"
HASH_METHOD = "sha256-manifest-v1"
TOOL_URL = "https://github.com/grcmana/skillbom"

# SPDX ids we emit as `license.id`; anything else is emitted as `license.name`
# so the BOM always validates against the CycloneDX schema's SPDX enum.
KNOWN_SPDX = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "Unlicense",
    "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-3.0-only", "AGPL-3.0-only",
})


def _prop(name: str, value: Any) -> dict[str, str]:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return {"name": f"{NS}:{name}", "value": str(value)}


def _license(value: str) -> list[dict[str, Any]]:
    value = value.strip()
    if value in KNOWN_SPDX:
        return [{"license": {"id": value}}]
    return [{"license": {"name": value}}]


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", s.lower()).strip("-")


def skill_component(s: Skill) -> dict[str, Any]:
    fm = s.frontmatter
    comp: dict[str, Any] = {"type": "application", "bom-ref": f"skill:{s.name}", "name": s.name}
    if s.version:
        comp["version"] = s.version
    if fm.get("description"):
        comp["description"] = str(fm["description"])
    author = s.metadata.get("author") or fm.get("author")
    if author:
        comp["authors"] = [{"name": str(author)}]
    if fm.get("license"):
        comp["licenses"] = _license(str(fm["license"]))
    comp["hashes"] = [{"alg": "SHA-256", "content": s.digest}]

    props = [
        _prop("kind", "skill"),
        _prop("path", s.rel_path),
        _prop("hash-method", HASH_METHOD),
        _prop("file-count", len(s.files)),
        _prop("has-scripts", str(any(f.role == "script" for f in s.files)).lower()),
    ]
    for k in sorted(fm):
        if k in ("name", "description", "license", "metadata"):
            continue
        props.append(_prop(f"frontmatter:{_key(k)}", fm[k]))
    for k in sorted(s.metadata):
        if k in ("author", "version"):
            continue
        props.append(_prop(f"meta:{_key(k)}", s.metadata[k]))
    comp["properties"] = props

    comp["components"] = [
        {
            "type": "file",
            "bom-ref": f"skill:{s.name}/file:{f.path}",
            "name": f.path,
            "hashes": [{"alg": "SHA-256", "content": f.sha256}],
            "properties": [_prop("role", f.role), _prop("size", f.size)],
        }
        for f in s.files
    ]
    return comp


def knowledge_component(k: Knowledge) -> dict[str, Any]:
    fm = k.frontmatter
    comp: dict[str, Any] = {"type": "data", "bom-ref": k.ref, "name": k.filename.rsplit(".", 1)[0]}
    if fm.get("version"):
        comp["version"] = str(fm["version"])
    title = fm.get("framework") or fm.get("title")
    if title:
        comp["description"] = str(title)
    comp["hashes"] = [{"alg": "SHA-256", "content": k.sha256}]
    props = [_prop("kind", "knowledge"), _prop("filename", k.filename)]
    if fm.get("as_of"):
        props.append(_prop("as-of", fm["as_of"]))
    for key in ("scheme_version", "licence_note", "license_note"):
        if fm.get(key):
            props.append(_prop(f"knowledge:{_key(key)}", fm[key]))
    comp["properties"] = props
    return comp


def _timestamp(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde and sde.isdigit():
        return datetime.fromtimestamp(int(sde), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _purl(repo_url: str | None, version: str | None) -> str | None:
    if not repo_url:
        return None
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", repo_url)
    if not m:
        return None
    purl = f"pkg:github/{m.group(1).lower()}/{m.group(2).lower()}"
    return f"{purl}@{version}" if version else purl


def build_bom(
    skills: list[Skill],
    *,
    name: str,
    version: str | None = None,
    repo_url: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    aggregate = hashlib.sha256(
        "".join(f"{s.digest}  {s.name}\n" for s in sorted(skills, key=lambda s: s.name.encode())).encode()
    ).hexdigest()
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"{TOOL_URL}#{name}@{version or ''}#{aggregate}")

    subject: dict[str, Any] = {"type": "application", "bom-ref": "subject", "name": name}
    if version:
        subject["version"] = version
    purl = _purl(repo_url, version)
    if purl:
        subject["purl"] = purl
    subject["hashes"] = [{"alg": "SHA-256", "content": aggregate}]
    if repo_url:
        subject["externalReferences"] = [{"type": "vcs", "url": repo_url}]

    metadata: dict[str, Any] = {}
    ts = _timestamp(timestamp)
    if ts:
        metadata["timestamp"] = ts
    metadata["tools"] = {"components": [{
        "type": "application", "name": "skillbom", "version": __version__,
        "externalReferences": [{"type": "vcs", "url": TOOL_URL}],
    }]}
    metadata["component"] = subject
    metadata["properties"] = [
        _prop("profile", PROFILE_VERSION),
        _prop("hash-method", HASH_METHOD),
        _prop("skill-count", len(skills)),
    ]

    skills = sorted(skills, key=lambda s: s.name.encode())
    knowledge: dict[str, Knowledge] = {}
    for s in skills:
        for k in s.knowledge:
            knowledge.setdefault(k.ref, k)

    components = [skill_component(s) for s in skills]
    components += [knowledge_component(knowledge[r]) for r in sorted(knowledge)]

    deps = [{"ref": "subject", "dependsOn": [f"skill:{s.name}" for s in skills]}]
    for s in skills:
        deps.append({"ref": f"skill:{s.name}", "dependsOn": sorted({k.ref for k in s.knowledge})})
    deps += [{"ref": r, "dependsOn": []} for r in sorted(knowledge)]

    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": metadata,
        "components": components,
        "dependencies": deps,
    }


def dumps(bom: dict[str, Any]) -> str:
    return json.dumps(bom, indent=2, ensure_ascii=False) + "\n"
