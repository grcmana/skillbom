"""Stdlib unittest suite. Run: PYTHONPATH=src python -m unittest discover -s tests -v"""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

from skillbom import check, frontmatter, generate, verify
from skillbom.cli import main
from skillbom.model import SkillError, load_skills

FIXTURE = Path(__file__).parent / "fixtures" / "repo"


def run_cli(*args: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue() + err.getvalue()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def bom(self, root: Path | None = None) -> dict:
        return generate.build_bom(load_skills(root or self.repo), name="fixture", version="v1.0.0",
                                  repo_url="https://github.com/example/fixture")


class FrontmatterTests(unittest.TestCase):
    def test_nested_quoted_and_lists(self) -> None:
        fm, body = frontmatter.read(
            '---\nname: a\nlicense: MIT\nmetadata:\n  version: 0.1.0\n  summary: "x: y"\n'
            '  tags: [one, "two, three"]\nallowed-tools:\n  - Read\n  - Write\n---\nbody\n')
        self.assertEqual(fm["metadata"], {"version": "0.1.0", "summary": "x: y", "tags": ["one", "two, three"]})
        self.assertEqual(fm["allowed-tools"], ["Read", "Write"])
        self.assertEqual(body.strip(), "body")

    def test_block_scalars(self) -> None:
        fm, _ = frontmatter.read("---\ndescription: >\n  one\n  two\nnotes: |\n  a\n  b\n---\n")
        self.assertEqual(fm["description"], "one two")
        self.assertEqual(fm["notes"], "a\nb")

    def test_rejects_unclosed_and_duplicates(self) -> None:
        with self.assertRaises(frontmatter.FrontmatterError):
            frontmatter.read("---\nname: a\n")
        with self.assertRaises(frontmatter.FrontmatterError):
            frontmatter.read("---\nname: a\nname: b\n---\n")

    def test_no_frontmatter(self) -> None:
        self.assertEqual(frontmatter.read("# hi\n")[0], {})


class GenerateTests(Base):
    def test_deterministic(self) -> None:
        self.assertEqual(generate.dumps(self.bom()), generate.dumps(self.bom()))

    def test_hash_independent_of_location(self) -> None:
        moved = self.tmp / "elsewhere" / "nested"
        shutil.copytree(self.repo / "skills", moved)
        a = {c["name"]: c["hashes"][0]["content"] for c in self.bom()["components"]}
        b = {c["name"]: c["hashes"][0]["content"] for c in self.bom(moved)["components"]}
        self.assertEqual(a, b)

    def test_structure(self) -> None:
        bom = self.bom()
        self.assertEqual(bom["specVersion"], "1.6")
        skills = [c for c in bom["components"] if c["type"] == "application"]
        self.assertEqual([s["name"] for s in skills], ["alpha", "beta"])
        alpha = skills[0]
        self.assertEqual(alpha["version"], "1.2.0")
        self.assertEqual(alpha["licenses"], [{"license": {"id": "MIT"}}])
        files = {f["name"] for f in alpha["components"]}
        self.assertEqual(files, {"SKILL.md", "references/pack.md", "scripts/score.py"})
        props = {p["name"]: p["value"] for p in alpha["properties"]}
        self.assertEqual(props["skillbom:has-scripts"], "true")
        self.assertEqual(props["skillbom:meta:maturity"], "experimental")
        self.assertEqual(bom["metadata"]["component"]["purl"], "pkg:github/example/fixture@v1.0.0")

    def test_property_names_follow_spec(self) -> None:
        import re
        names = set()

        def walk(c: dict) -> None:
            names.update(p["name"] for p in c.get("properties", []))
            for sub in c.get("components", []):
                walk(sub)
        bom = self.bom()
        walk(bom["metadata"])
        for c in bom["components"]:
            walk(c)
        bad = [n for n in names if not re.fullmatch(r"skillbom:[a-z0-9.-]+(:[a-z0-9.-]+)*", n)]
        self.assertEqual(bad, [])
        self.assertIn("skillbom:knowledge:licence-note", names)

    def test_shared_knowledge_deduplicated(self) -> None:
        bom = self.bom()
        packs = [c for c in bom["components"] if c["type"] == "data"]
        self.assertEqual(len(packs), 1)
        props = {p["name"]: p["value"] for p in packs[0]["properties"]}
        self.assertEqual(props["skillbom:as-of"], "2026-10-01")
        deps = {d["ref"]: d["dependsOn"] for d in bom["dependencies"]}
        self.assertEqual(deps["skill:alpha"], deps["skill:beta"])

    def test_excluded_files_ignored(self) -> None:
        before = self.bom()["components"][0]["hashes"]
        (self.repo / "skills/alpha/.DS_Store").write_bytes(b"x")
        self.assertEqual(self.bom()["components"][0]["hashes"], before)

    def test_symlink_rejected(self) -> None:
        (self.repo / "skills/alpha/link.md").symlink_to(self.repo / "skills/beta/SKILL.md")
        with self.assertRaises(SkillError):
            load_skills(self.repo)

    def test_duplicate_names_rejected(self) -> None:
        shutil.copytree(self.repo / "skills/alpha", self.repo / "other/alpha")
        with self.assertRaises(SkillError):
            load_skills(self.repo)

    def test_schema_valid(self) -> None:
        try:
            from cyclonedx.schema import SchemaVersion
            from cyclonedx.validation.json import JsonStrictValidator
        except ImportError:
            self.skipTest("cyclonedx-python-lib[json-validation] not installed")
        err = JsonStrictValidator(SchemaVersion.V1_6).validate_str(generate.dumps(self.bom()))
        self.assertIsNone(err, str(err))


class CheckTests(Base):
    def findings(self, bom: dict, today: str = "2026-11-01", policy: dict | None = None):
        pol = check.load_policy(None)
        if policy:
            for k, v in policy.items():
                pol["rules"][k].update(v)
        return check.run(bom, pol, date.fromisoformat(today))

    def test_fixture_passes(self) -> None:
        errors = [f for f in self.findings(self.bom()) if f.severity == "error"]
        self.assertEqual(errors, [])

    def test_missing_version_and_licence(self) -> None:
        p = self.repo / "skills/beta/SKILL.md"
        p.write_text(p.read_text().replace("license: Apache-2.0\n", "").replace("  version: 0.1.0\n", ""))
        rules = {f.rule for f in self.findings(self.bom()) if f.severity == "error"}
        self.assertTrue({"skill-version", "skill-license"} <= rules)

    def test_name_mismatch(self) -> None:
        p = self.repo / "skills/beta/SKILL.md"
        p.write_text(p.read_text().replace("name: beta", "name: gamma"))
        self.assertIn("skill-name-matches-folder", {f.rule for f in self.findings(self.bom())})

    def test_stale_knowledge_warns_then_errors(self) -> None:
        f = self.findings(self.bom(), today="2027-10-01")
        self.assertEqual({(x.rule, x.severity) for x in f}, {("knowledge-freshness", "warn")})
        f = self.findings(self.bom(), today="2027-10-01", policy={"knowledge-freshness": {"severity": "error"}})
        self.assertEqual({x.severity for x in f}, {"error"})

    def test_tampered_hash(self) -> None:
        bom = self.bom()
        bom["components"][0]["hashes"][0]["content"] = "nothex"
        self.assertIn("skill-hash", {f.rule for f in self.findings(bom)})

    def test_unknown_policy_rule(self) -> None:
        pol = self.tmp / "p.json"
        pol.write_text(json.dumps({"rules": {"nope": {}}}))
        with self.assertRaises(ValueError):
            check.load_policy(pol)


class VerifyTests(Base):
    def test_clean_and_drift(self) -> None:
        bom = self.bom()
        self.assertTrue(all(d.status == "ok" for d in verify.compare(load_skills(self.repo), bom)))
        (self.repo / "skills/alpha/SKILL.md").write_text("tampered", encoding="utf-8")
        (self.repo / "skills/alpha/scripts/extra.sh").write_text("curl evil", encoding="utf-8")
        (self.repo / "skills/alpha/references/pack.md").unlink()
        d = {x.name: x for x in verify.compare(load_skills(self.repo), bom)}
        self.assertEqual(d["alpha"].status, "modified")
        self.assertEqual(d["alpha"].added, ["scripts/extra.sh"])
        self.assertEqual(d["alpha"].removed, ["references/pack.md"])
        self.assertEqual(d["alpha"].changed, ["SKILL.md"])

    def test_partial_install_and_unknown(self) -> None:
        bom = self.bom()
        shutil.rmtree(self.repo / "skills/beta")
        statuses = {d.name: d.status for d in verify.compare(load_skills(self.repo), bom)}
        self.assertEqual(statuses["beta"], "not-installed")
        bom["components"] = [c for c in bom["components"] if c["name"] != "alpha"]
        statuses = {d.name: d.status for d in verify.compare(load_skills(self.repo), bom)}
        self.assertEqual(statuses["alpha"], "not-in-bom")


class CliTests(Base):
    def test_end_to_end(self) -> None:
        out = self.tmp / "bom.json"
        self.assertEqual(run_cli("generate", str(self.repo), "-o", str(out), "--version", "v1.0.0")[0], 0)
        self.assertEqual(run_cli("check", str(out), "--today", "2026-11-01")[0], 0)
        self.assertEqual(run_cli("verify", str(self.repo / "skills"), "--bom", str(out))[0], 0)
        shutil.rmtree(self.repo / "skills/beta")
        self.assertEqual(run_cli("verify", str(self.repo), "--bom", str(out))[0], 0)
        self.assertEqual(run_cli("verify", str(self.repo), "--bom", str(out), "--require-all")[0], 1)
        code, text = run_cli("check", str(out), "--json", "--today", "2026-11-01")
        self.assertTrue(json.loads(text)["ok"])

    def test_verify_finds_bom(self) -> None:
        import os
        skills = self.repo / "skills"
        text = generate.dumps(self.bom())
        cwd = os.getcwd()
        try:
            os.chdir(self.tmp)
            self.assertEqual(run_cli("verify", str(skills))[0], 2)  # nothing to find
            (self.tmp / "skillbom.cdx.json").write_text(text)  # current folder
            self.assertEqual(run_cli("verify", str(skills))[0], 0)
            (self.tmp / "skillbom.cdx.json").unlink()
            (self.repo / "skillbom.cdx.json").write_text(text)  # parent of skills folder
            code, out = run_cli("verify", str(skills))
            self.assertEqual(code, 0)
            self.assertIn("using", out)
            (self.repo / "skillbom.cdx.json").unlink()
            (skills / "skillbom.cdx.json").write_text(text)  # inside the skills folder
            self.assertEqual(run_cli("verify", str(skills))[0], 0)
        finally:
            os.chdir(cwd)

    def test_bad_input_exit_2(self) -> None:
        self.assertEqual(run_cli("generate", str(self.tmp / "missing"))[0], 2)
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(run_cli("generate", str(empty))[0], 2)
        notbom = self.tmp / "x.json"
        notbom.write_text("{}")
        self.assertEqual(run_cli("check", str(notbom))[0], 2)


if __name__ == "__main__":
    unittest.main()
