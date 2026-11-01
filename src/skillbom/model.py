"""Read Agent Skills from disk and compute deterministic hashes (stdlib only)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import frontmatter

# Files and directories never included in a skill's content hash.
EXCLUDED_FILES = frozenset({".DS_Store", "Thumbs.db"})
EXCLUDED_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv"})
EXCLUDED_SUFFIXES = (".pyc",)
# Directories never searched for skills.
SKIP_SEARCH = EXCLUDED_DIRS | {".github", "dist", "build"}

ROLES = {"SKILL.md": "instructions", "references": "reference", "assets": "asset", "scripts": "script"}


class SkillError(Exception):
    """Input that cannot be turned into a trustworthy BOM."""


@dataclass
class SkillFile:
    path: str  # posix, relative to the skill directory
    sha256: str
    size: int

    @property
    def role(self) -> str:
        head = self.path.split("/", 1)[0]
        return ROLES.get(head, "other")


@dataclass
class Knowledge:
    """A reference file inside a skill, treated as a knowledge dependency."""
    filename: str
    sha256: str
    frontmatter: dict[str, Any]

    @property
    def ref(self) -> str:
        stem = self.filename.rsplit(".", 1)[0]
        return f"knowledge:{stem}@sha256:{self.sha256[:12]}"


@dataclass
class Skill:
    name: str
    folder: str
    rel_path: str
    frontmatter: dict[str, Any]
    files: list[SkillFile]
    knowledge: list[Knowledge] = field(default_factory=list)

    @property
    def digest(self) -> str:
        return manifest_digest(self.files)

    @property
    def metadata(self) -> dict[str, Any]:
        m = self.frontmatter.get("metadata")
        return m if isinstance(m, dict) else {}

    @property
    def version(self) -> str | None:
        v = self.metadata.get("version") or self.frontmatter.get("version")
        return str(v) if v else None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_digest(files: list[SkillFile]) -> str:
    """SHA-256 over a sha256sum-style manifest, sorted by UTF-8 path bytes.

    Equivalent to: for each file in byte-sorted path order, the line
    "<sha256hex>  <relpath>\\n", concatenated and hashed with SHA-256.
    """
    lines = "".join(f"{f.sha256}  {f.path}\n" for f in sorted(files, key=lambda f: f.path.encode()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _walk_files(skill_dir: Path) -> list[SkillFile]:
    out: list[SkillFile] = []
    for root, dirs, names in os.walk(skill_dir, followlinks=False):
        rootp = Path(root)
        for d in list(dirs):
            if (rootp / d).is_symlink():
                raise SkillError(f"symlinked directory not allowed: {(rootp / d).relative_to(skill_dir.parent)}")
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for n in sorted(names):
            p = rootp / n
            if n in EXCLUDED_FILES or n.endswith(EXCLUDED_SUFFIXES):
                continue
            if p.is_symlink():
                raise SkillError(f"symlink not allowed: {p.relative_to(skill_dir.parent)}")
            rel = p.relative_to(skill_dir).as_posix()
            if any(ch in rel for ch in "\n\r\\"):
                # These would make the hash manifest ambiguous.
                raise SkillError(f"file name not allowed (newline or backslash): {rel!r}")
            out.append(SkillFile(rel, sha256_file(p), p.stat().st_size))
    return sorted(out, key=lambda f: f.path.encode())


def find_skill_dirs(root: Path) -> list[Path]:
    """Every directory under root that contains a SKILL.md (not nested inside another skill)."""
    if (root / "SKILL.md").is_file():
        return [root]
    found: list[Path] = []
    for cur, dirs, names in os.walk(root, followlinks=False):
        curp = Path(cur)
        if "SKILL.md" in names and curp != root:
            found.append(curp)
            dirs[:] = []  # don't descend into a skill
            continue
        dirs[:] = sorted(d for d in dirs if d not in SKIP_SEARCH and not (curp / d).is_symlink())
    return sorted(found, key=lambda p: p.as_posix().encode())


def load_skill(skill_dir: Path, root: Path) -> Skill:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    try:
        fm, _ = frontmatter.read(text)
    except frontmatter.FrontmatterError as e:
        raise SkillError(f"{skill_dir.name}/SKILL.md: {e}") from e
    files = _walk_files(skill_dir)
    knowledge: list[Knowledge] = []
    ref_dir = skill_dir / "references"
    if ref_dir.is_dir():
        for f in files:
            if f.role == "reference" and f.path.count("/") == 1:
                kfm: dict[str, Any] = {}
                if f.path.endswith(".md"):
                    try:
                        kfm, _ = frontmatter.read((skill_dir / f.path).read_text(encoding="utf-8"))
                    except (frontmatter.FrontmatterError, UnicodeDecodeError):
                        kfm = {}
                knowledge.append(Knowledge(f.path.split("/", 1)[1], f.sha256, kfm))
    name = str(fm.get("name") or skill_dir.name)
    rel = skill_dir.relative_to(root).as_posix() if skill_dir != root else "."
    return Skill(name=name, folder=skill_dir.name, rel_path=rel, frontmatter=fm, files=files, knowledge=knowledge)


def load_skills(root: Path) -> list[Skill]:
    root = root.resolve()
    if not root.is_dir():
        raise SkillError(f"not a directory: {root}")
    skills = [load_skill(d, root) for d in find_skill_dirs(root)]
    seen: dict[str, str] = {}
    for s in skills:
        if s.name in seen:
            raise SkillError(f"duplicate skill name '{s.name}' in {seen[s.name]} and {s.rel_path}")
        seen[s.name] = s.rel_path
    return skills
