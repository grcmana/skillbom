# User guide

SkillBOM has two kinds of user:

- **Publishers** maintain a repository of skills and want to ship a signed BOM with each release. Start at [Publishing a Skill BOM](#publishing-a-skill-bom).
- **Users** install skills and want to check what they got. Start at [Checking skills you've installed](#checking-skills-youve-installed).

## Install

Python 3.10 or later. No other dependencies.

```sh
pip install "git+https://github.com/grcmana/skillbom@v0.0.1"
skillbom --version
```

To run from a clone without installing: `PYTHONPATH=src python -m skillbom --help`.

## Publishing a Skill BOM

### 1. Generate

From the root of your skills repository:

```sh
skillbom generate . \
  --name my-skills \
  --version v1.2.0 \
  --repo-url https://github.com/owner/my-skills \
  -o skillbom.cdx.json
```

| Option | Meaning |
|---|---|
| `path` | Folder to scan. Every folder containing a `SKILL.md` is a skill. `.git`, `.github`, `node_modules`, `.venv`, `dist` and `build` are skipped. |
| `--name` | Name of the collection. Defaults to the folder name. |
| `--version` | Release version, e.g. your tag. |
| `--repo-url` | Source repository. GitHub URLs also produce a package URL (`pkg:github/owner/repo@version`). |
| `--timestamp` | ISO 8601 time to record. Defaults to `SOURCE_DATE_EPOCH` if set, otherwise no timestamp. |
| `-o` | Output file. Defaults to standard output. |

Output is deterministic: the same files always produce a byte-identical BOM. To include a reproducible timestamp, set `SOURCE_DATE_EPOCH` to your release commit's time:

```sh
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) skillbom generate . --name my-skills --version v1.2.0 -o skillbom.cdx.json
```

**What it reads from each `SKILL.md`:** `name`, `description`, `license`, `metadata.version` (or a top-level `version`), `metadata.author`. Any other frontmatter field is kept as a `skillbom:frontmatter:` or `skillbom:meta:` property, so fields like `allowed-tools` or `maturity` appear in the BOM without extra work.

**Knowledge files:** each file directly inside a skill's `references/` folder is recorded as knowledge. If it has YAML frontmatter, these fields are picked up:

```yaml
---
framework: ISO/IEC 27001:2022     # shown as the description
as_of: 2026-10-29                 # date last checked against the source; drives freshness checks
version: 1.0.0                    # optional
---
```

### 2. Check

```sh
skillbom check skillbom.cdx.json
```

Each rule produces findings at `error` or `warn` severity. Errors fail the check (exit code `1`).

| Rule | Default | Fails when |
|---|---|---|
| `bom-profile` | error | Not CycloneDX 1.6, not a Skill BOM, or no skills found |
| `skill-version` | error | A skill declares no version |
| `skill-semver` | warn | A version isn't `MAJOR.MINOR.PATCH` |
| `skill-hash` | error | A skill or file has no valid SHA-256 fingerprint |
| `skill-license` | error | A skill declares no licence |
| `skill-name-matches-folder` | error | `name` in `SKILL.md` differs from the folder name |
| `required-metadata` | error | A required metadata field is missing (default: `author`) |
| `knowledge-freshness` | warn | A knowledge file's `as_of` date is more than 183 days old |

**Custom policy.** Override any rule in a JSON file. Unknown rule names are rejected, so typos don't silently pass.

```json
{
  "rules": {
    "knowledge-freshness": { "severity": "error", "max_age_days": 90, "require_as_of": true },
    "required-metadata": { "keys": ["author", "maturity"] },
    "skill-semver": { "severity": "off" }
  }
}
```

```sh
skillbom check skillbom.cdx.json --policy policy.json
skillbom check skillbom.cdx.json --today 2026-11-01   # evaluate freshness as of a fixed date
skillbom check skillbom.cdx.json --json               # machine-readable
```

### 3. Sign and publish in GitHub Actions

Add this to your release workflow. It generates, checks, signs and attaches the BOM whenever you push a version tag.

```yaml
name: release
on:
  push:
    tags: ["v*"]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write        # attach to the release
      id-token: write        # keyless signing
      attestations: write    # store the attestation
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
      - run: pip install "git+https://github.com/grcmana/skillbom@v0.0.1"
      - name: Generate and check the Skill BOM
        run: |
          export SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
          skillbom generate . --name ${{ github.event.repository.name }} \
            --version ${{ github.ref_name }} \
            --repo-url ${{ github.server_url }}/${{ github.repository }} \
            -o skillbom.cdx.json
          skillbom check skillbom.cdx.json
      - name: Sign
        uses: actions/attest@v4
        with:
          subject-path: skillbom.cdx.json
      - name: Attach to release
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release upload "${{ github.ref_name }}" skillbom.cdx.json --clobber
```

The last step assumes the release already exists. If your workflow creates it, attach the file there instead.

Pin SkillBOM to a tag, as above, so a new SkillBOM version can't change your release output unexpectedly.

### 4. Check on every pull request (optional)

Running `check` in CI catches problems before release, such as a skill with no version or a stale knowledge pack:

```yaml
- run: |
    skillbom generate . --name my-skills -o /tmp/skillbom.cdx.json
    skillbom check /tmp/skillbom.cdx.json
```

## Checking skills you've installed

### 1. Get the publisher's BOM

Download `skillbom.cdx.json` from the release of the skills you installed, and save it next to your skills folder. For Claude Code that's usually:

```
your-project/
  .claude/
    skills/              ← installed skills
    skillbom.cdx.json    ← save the BOM here
```

Don't put it inside an individual skill's folder: it would then count as part of that skill and show up as drift.

### 2. Check the signature

Confirm the BOM really came from the publisher's release workflow and hasn't been altered (needs the [GitHub CLI](https://cli.github.com)):

```sh
gh attestation verify .claude/skillbom.cdx.json --repo owner/skills-repo
```

If this fails, stop: don't trust the BOM.

### 3. Verify

```sh
skillbom verify .claude/skills
```

SkillBOM looks for `skillbom.cdx.json` in the skills folder, then its parent, then the current folder. Use `--bom <file>` to point at a specific file.

```
using /home/me/project/.claude/skillbom.cdx.json
OK            dpia
MODIFIED      risk-register
    changed  SKILL.md
FAIL: 1 matching, 1 drifted or unknown
```

| Status | Meaning | Fails? |
|---|---|---|
| `OK` | Every file matches the release | No |
| `MODIFIED` | Files were added, removed or changed since release; each is listed | Yes |
| `NOT-IN-BOM` | You have a skill the BOM doesn't mention | Yes |
| `NOT-INSTALLED` | The BOM lists a skill you haven't installed | Only with `--require-all` |

Installing only some skills from a collection is normal, so missing skills are ignored by default. Use `--require-all` if you installed the full set and want to confirm nothing is missing.

`--json` gives machine-readable output, for example to run `verify` in your own CI.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Passed |
| `1` | `check` found an error, or `verify` found drift |
| `2` | Bad input: missing folder, no skills found, not a BOM, unreadable frontmatter, a symlink, or an ambiguous file name |

## Troubleshooting

**"symlink not allowed"**
A skill contains a symbolic link. SkillBOM refuses to describe it, because a link can point outside the skill and its target could change without the skill's fingerprint changing. Replace the link with a real copy of the file.

**"file name not allowed (newline or backslash)"**
A file path contains a newline, carriage return or backslash. These would make the fingerprint ambiguous. Rename the file.

**Frontmatter errors** (e.g. "flow mappings are not supported")
SkillBOM reads a deliberately small, predictable subset of YAML: plain and quoted values, nested sections, lists, and `|` / `>` text blocks. It stops rather than guessing if it meets anything else, such as `{a: b}` inline mappings or lists of mappings. Rewrite that field in block style.

**"duplicate skill name"**
Two folders declare the same `name`. Each skill in a collection needs a unique name.

**`verify` says everything is modified**
Usually line endings. Fingerprints are computed on exact bytes, so a checkout that converts line endings (for example Git's `core.autocrlf` on Windows) produces different files. Install skills without line-ending conversion.

**`check` warns about freshness on a new release**
The publisher's `as_of` date is older than the policy allows. This is a warning by default; it's a prompt to review the knowledge, not proof it's wrong.

**No timestamp in the BOM**
Expected unless you set `SOURCE_DATE_EPOCH` or `--timestamp`. Leaving it out keeps the output reproducible.
