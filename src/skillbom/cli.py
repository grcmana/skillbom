"""skillbom command line. Exit codes: 0 ok, 1 policy failure or drift, 2 bad input."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__, check, generate, verify
from .model import SkillError, load_skills


def _err(msg: str) -> int:
    print(f"skillbom: error: {msg}", file=sys.stderr)
    return 2


def _load_bom(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("bomFormat") != "CycloneDX":
        raise ValueError(f"{path} is not a CycloneDX JSON BOM")
    return data


def cmd_generate(a: argparse.Namespace) -> int:
    root = Path(a.path)
    skills = load_skills(root)
    if not skills:
        return _err(f"no SKILL.md files found under {root}")
    bom = generate.build_bom(
        skills, name=a.name or root.resolve().name, version=a.version,
        repo_url=a.repo_url, timestamp=a.timestamp,
    )
    text = generate.dumps(bom)
    if a.output == "-":
        sys.stdout.write(text)
    else:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"wrote {a.output}: {len(skills)} skills", file=sys.stderr)
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    bom = _load_bom(a.bom)
    policy = check.load_policy(Path(a.policy) if a.policy else None)
    today = date.fromisoformat(a.today) if a.today else date.today()
    findings = check.run(bom, policy, today)
    errors = [f for f in findings if f.severity == "error"]
    if a.json:
        json.dump({"ok": not errors, "today": today.isoformat(),
                   "findings": [f.as_dict() for f in findings]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for f in findings:
            print(f"{f.severity.upper():5}  {f.rule:28} {f.target}: {f.message}")
        warns = len(findings) - len(errors)
        print(f"{'FAIL' if errors else 'PASS'}: {len(errors)} error(s), {warns} warning(s)")
    return 1 if errors else 0


BOM_FILENAME = "skillbom.cdx.json"


def find_bom(skills_dir: Path) -> Path | None:
    """Look for the conventional BOM file next to the skills: in the folder,
    its parent, then the current directory. Never touches the network."""
    seen = []
    # A BOM placed inside a single skill's folder would itself count as drift,
    # so only look inside skills_dir when it is a folder *of* skills.
    first = [] if (skills_dir / "SKILL.md").is_file() else [skills_dir]
    for d in (*first, skills_dir.resolve().parent, Path.cwd()):
        cand = (d / BOM_FILENAME).resolve()
        if cand not in seen:
            seen.append(cand)
            if cand.is_file():
                return cand
    return None


def cmd_verify(a: argparse.Namespace) -> int:
    bom_path = Path(a.bom) if a.bom else find_bom(Path(a.path))
    if bom_path is None:
        return _err(
            f"no {BOM_FILENAME} found in {a.path}, its parent folder or the current folder. "
            "Download the BOM from the skills' release and save it there, or pass --bom <file>."
        )
    if not a.bom and not a.json:
        print(f"using {bom_path}", file=sys.stderr)
    bom = _load_bom(str(bom_path))
    installed = load_skills(Path(a.path))
    if not installed:
        return _err(f"no SKILL.md files found under {a.path}")
    diffs = verify.compare(installed, bom)
    bad = {"modified", "not-in-bom"} | ({"not-installed"} if a.require_all else set())
    failed = [d for d in diffs if d.status in bad]
    if a.json:
        json.dump({"ok": not failed, "skills": [d.as_dict() for d in diffs]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for d in diffs:
            if d.status == "not-installed" and not a.require_all:
                continue
            print(f"{d.status.upper():13} {d.name}")
            for k in ("added", "removed", "changed"):
                for p in getattr(d, k):
                    print(f"    {k:8} {p}")
        ok = sum(d.status == "ok" for d in diffs)
        print(f"{'FAIL' if failed else 'PASS'}: {ok} matching, {len(failed)} drifted or unknown")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillbom", description="A verifiable bill of materials for agent skills.")
    p.add_argument("--version", action="version", version=f"skillbom {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build a CycloneDX Skill BOM from a directory of skills")
    g.add_argument("path", help="repository or directory containing SKILL.md folders")
    g.add_argument("-o", "--output", default="-", help="output file (default: stdout)")
    g.add_argument("--name", help="name of the skills collection (default: directory name)")
    g.add_argument("--version", dest="version", help="release version, e.g. v0.1.0")
    g.add_argument("--repo-url", help="source repository URL, e.g. https://github.com/owner/repo")
    g.add_argument("--timestamp", help="ISO 8601 timestamp (default: SOURCE_DATE_EPOCH, else omitted)")
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("check", help="apply policy rules to a Skill BOM")
    c.add_argument("bom", help="path to a Skill BOM (CycloneDX JSON)")
    c.add_argument("--policy", help="JSON policy file overriding the defaults")
    c.add_argument("--today", help="evaluate freshness as of this date (YYYY-MM-DD)")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    c.set_defaults(func=cmd_check)

    v = sub.add_parser("verify", help="compare installed skills against a Skill BOM")
    v.add_argument("path", help="directory of installed skills, e.g. .claude/skills")
    v.add_argument("--bom", help=f"path to the released Skill BOM (default: find {BOM_FILENAME} "
                                  "in the skills folder, its parent, or the current folder)")
    v.add_argument("--require-all", action="store_true", help="fail if any skill in the BOM is not installed")
    v.add_argument("--json", action="store_true", help="machine-readable output")
    v.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SkillError, ValueError, OSError) as e:
        return _err(str(e))


if __name__ == "__main__":
    sys.exit(main())
