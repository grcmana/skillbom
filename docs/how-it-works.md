# How SkillBOM works

This page explains SkillBOM in plain English. You don't need to know what an SBOM is to follow it.

## The problem

An agent skill is a folder of instructions, reference material and sometimes scripts that an AI agent follows. Installing one is like hiring a contractor and handing them your procedures manual: what they do depends on what's in that folder.

Today, most people install skills with one command and never look again. That leaves basic questions unanswered:

- **Is this the version that was released, or has something in it changed?**
- **What material is it relying on, and how old is that material?**
- **Does it include code that can run on my machine?**

A software bill of materials (SBOM) answers questions like these for software: it's a list of every ingredient, with a fingerprint of each one. SkillBOM does the same for agent skills.

## The idea in one picture

```
  Skill folder                     Skill BOM (skillbom.cdx.json)
  ─────────────                    ──────────────────────────────
  dpia/                            skill: dpia  v0.1.0  MIT  GRCMANA
    SKILL.md            ──hash──►    fingerprint of the whole folder
    assets/template.md  ──hash──►    fingerprint of every file, with its role
    references/gdpr.md  ──hash──►    knowledge: gdpr  (checked as of 2026-10-29)
    references/...
                                   + signature: who produced this BOM
```

Three things happen:

1. **Fingerprint.** Every file gets a SHA-256 hash: a fingerprint that changes completely if even one character changes. The whole folder gets one combined fingerprint.
2. **Describe.** The BOM records each skill's name, version, licence and author, what role each file plays (instructions, reference, asset, script), and which reference material it ships, with the date that material was last checked.
3. **Sign.** The publisher signs the BOM when they release, so you can check it came from them and hasn't been altered.

## A worked example: the `dpia` skill

This is real data from [`examples/grcskills-v0.1.0.cdx.json`](../examples/grcskills-v0.1.0.cdx.json), the BOM for GRC Skills v0.1.0.

**What the skill is**

| | |
|---|---|
| Name and version | `dpia` 0.1.0 |
| Folder fingerprint | `0e16275d…25050a7` |
| Files | 5 |
| Ships scripts? | No |

**What's in it**

| File | Role |
|---|---|
| `SKILL.md` | instructions |
| `assets/dpia-template.md` | asset |
| `references/gdpr.md` | reference |
| `references/grc-workspace.md` | reference |
| `references/risk-methodology.md` | reference |

**What it was built from.** The three reference files are recorded as *knowledge*. The GDPR pack declares it was last checked against its sources on 2026-10-29. The same GDPR pack ships inside other GRC Skills too; the BOM lists it once and links it to every skill that uses it, so if the pack changes you can see every skill affected.

## The three commands

| Command | Who runs it | Question it answers |
|---|---|---|
| `skillbom generate` | The skill publisher, at release | "What exactly are we releasing?" |
| `skillbom check` | The publisher in CI, or anyone reviewing a BOM | "Does this release meet our rules?" (versions, licences, fingerprints, how old the knowledge is) |
| `skillbom verify` | The skill user, after installing | "Is what I installed what was released?" |

If someone edits `SKILL.md` after release, or adds a script, `verify` reports exactly which files changed:

```
MODIFIED      dpia
    added    scripts/extra.sh
    changed  SKILL.md
```

## Where evidence fits

A BOM describes a skill. It doesn't say whether the skill is any good. That needs testing: running the skill against cases with known right answers. In the wider picture:

| Layer | Job | Example |
|---|---|---|
| Evals | Test the skill and score it | [GRC Evals](https://grcevals.io) (planned) |
| SkillBOM | Record what the skill is, and link to its test results | This project |
| Signing | Prove who produced the record | GitHub artifact attestations |

Profile 0.2 will add evidence: a test result recorded against the exact fingerprint it was produced on. If the skill changes after testing, the fingerprints no longer match and the result is flagged as out of date.

## What SkillBOM proves, and what it doesn't

| It proves | It doesn't prove |
|---|---|
| The files you have match the files that were released | That the skill gives correct or safe advice |
| Who produced the BOM (once signed), and that it hasn't changed since | That the publisher is trustworthy |
| Which knowledge each skill ships, and the date the author declared for it | That the knowledge is actually up to date; the date is the author's claim |
| Whether a skill ships executable scripts | What those scripts do |

The [architecture page](architecture.md#threat-model) sets out what kinds of tampering SkillBOM catches, and what it doesn't.

## Next

- [User guide](user-guide.md): how to publish or verify a BOM, step by step
- [SPEC.md](../SPEC.md): the exact format, for anyone building their own tooling
