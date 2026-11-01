# Security policy

SkillBOM is used to decide whether agent skills can be trusted. A flaw that makes a tampered skill look genuine is a security issue.

## What to report privately
- A way to change a skill's files without `skillbom verify` detecting it (e.g. a hashing gap, a path or symlink trick, an exclusion that can be abused).
- A way to make `skillbom check` pass a BOM that should fail.
- A crafted `SKILL.md` or BOM that makes the CLI read or write files outside the target directory, or run code.
- Weaknesses in this repository's release or signing workflow.

## How to report
Use **[Report a vulnerability](https://github.com/grcmana/skillbom/security/advisories/new)** (GitHub private vulnerability reporting). Please don't open a public issue.

We aim to acknowledge reports within 5 working days, and to agree a fix and disclosure timeline with you.

## Not security issues
Problems with the content of a skill described by a BOM belong to that skill's maintainers. A disagreement about the profile's design is welcome as a normal issue.
