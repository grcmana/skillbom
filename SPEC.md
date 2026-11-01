# Skill BOM Profile for CycloneDX

**Profile version:** 0.1 (draft, experimental)
**Base standard:** CycloneDX 1.6 (JSON)
**Licence:** this document is CC-BY-4.0. The reference implementation is Apache-2.0.

A Skill BOM describes a collection of [Agent Skills](https://agentskills.io) (folders containing a `SKILL.md`) as a CycloneDX bill of materials. It answers four questions about each skill:

1. **What is it?** Name, version, licence, author, and the exact files it contains.
2. **Has it changed?** A content hash of the whole skill folder, plus a hash for every file.
3. **What was it built from?** The knowledge and reference files it ships, and how current they are.
4. **What evidence backs it?** Reserved for profile 0.2: eval results and review records, pinned to the content hash they were produced against.

A Skill BOM is a profile, not a new format. It is a valid CycloneDX 1.6 document and opens in existing SBOM tooling. Everything specific to this profile is carried in standard CycloneDX fields or in properties under the `skillbom:` namespace.

The key words MUST, SHOULD and MAY are used as in RFC 2119.

## 1. What a Skill BOM does not claim

- A Skill BOM records what a skill **is**. It does not say the skill is correct, safe or effective.
- A signature or attestation over a Skill BOM proves **who produced it and that it hasn't changed since**. It does not prove the contents are true.
- Freshness dates (`as-of`) are declared by the skill author. The profile records them; it doesn't verify them.

## 2. Document

| Field | Requirement |
|---|---|
| `bomFormat` | MUST be `CycloneDX` |
| `specVersion` | MUST be `1.6` |
| `serialNumber` | MUST be a `urn:uuid`. Generators SHOULD derive it deterministically (UUIDv5 over subject name, version and aggregate hash) so identical input yields an identical BOM. |
| `metadata.timestamp` | OPTIONAL. Generators SHOULD take it from `SOURCE_DATE_EPOCH` (e.g. the release commit time) and omit it otherwise, to keep output reproducible. |
| `metadata.tools.components` | SHOULD name the generator and its version |
| `metadata.component` | The collection being described (e.g. a skills repository at a release). `bom-ref` MUST be `subject`. SHOULD carry `version`, `purl` and a `vcs` external reference. Its SHA-256 hash is the **aggregate hash** (§5.3). |
| `metadata.properties` | MUST include `skillbom:profile` = `0.1` and `skillbom:hash-method` = `sha256-manifest-v1` |

## 3. Skill components

Each skill is a top-level component.

| Field | Source | Requirement |
|---|---|---|
| `type` | — | `application` |
| `bom-ref` | — | `skill:<name>` |
| `name` | `name` in SKILL.md frontmatter (folder name if absent) | MUST |
| `version` | `metadata.version`, else top-level `version` | SHOULD (semantic versioning) |
| `description` | `description` | SHOULD |
| `authors[].name` | `metadata.author`, else `author` | SHOULD |
| `licenses` | `license` | SHOULD. Emitted as an SPDX `id` when recognised, otherwise as a licence `name`. |
| `hashes` | §5.2 | MUST contain one `SHA-256` entry: the skill content hash |
| `components` | §3.1 | MUST list every hashed file |

Skill properties:

| Property | Meaning |
|---|---|
| `skillbom:kind` | `skill` (MUST) |
| `skillbom:path` | Folder path relative to the scanned root |
| `skillbom:hash-method` | `sha256-manifest-v1` |
| `skillbom:file-count` | Number of hashed files |
| `skillbom:has-scripts` | `true` if the skill ships anything under `scripts/` |
| `skillbom:frontmatter:<key>` | Any other top-level frontmatter field (e.g. `allowed-tools`), lists joined with `, ` |
| `skillbom:meta:<key>` | Any field under `metadata` other than `author` and `version` (e.g. `maturity`, `collection`, `frameworks`) |

### 3.1 File components

Every file in the skill folder (after exclusions, §5.1) is a nested component:

- `type`: `file`; `bom-ref`: `skill:<name>/file:<relative path>`; `name`: path relative to the skill folder, `/`-separated
- `hashes`: one `SHA-256`
- `skillbom:role`: `instructions` (`SKILL.md`), `reference` (`references/`), `asset` (`assets/`), `script` (`scripts/`) or `other`
- `skillbom:size`: bytes

Roles make capabilities visible: a reviewer can see at a glance whether a skill ships executable scripts.

## 4. Knowledge components

Files directly inside a skill's `references/` folder are treated as **knowledge**: the material a skill relies on. Each distinct file (by content hash) appears once as a top-level component, even if several skills ship it.

| Field | Value |
|---|---|
| `type` | `data` |
| `bom-ref` | `knowledge:<file stem>@sha256:<first 12 hex of hash>` (content-addressed) |
| `name` | File stem |
| `version` | `version` from the file's frontmatter, if present |
| `description` | `framework` or `title` from frontmatter, if present |
| `hashes` | One `SHA-256` of the file |

Properties: `skillbom:kind` = `knowledge`, `skillbom:filename`, and if declared, `skillbom:as-of` (ISO date the content was last checked against its source). Recognised extras: `skillbom:knowledge:scheme-version`, `skillbom:knowledge:licence-note`.

### 4.1 Dependencies

- `subject` depends on every skill.
- Each skill depends on the knowledge components it ships.

This makes shared knowledge visible: when a framework pack changes, every dependent skill is identifiable.

## 5. Hashing

### 5.1 Exclusions
Not hashed: `.DS_Store`, `Thumbs.db`, `*.pyc`, and directories named `.git`, `__pycache__`, `node_modules`, `.venv`. Symlinks are rejected: a generator MUST fail rather than follow or skip them, because a link can point outside the skill. File paths containing a newline, carriage return or backslash are also rejected, because they would make the manifest in §5.2 ambiguous.

### 5.2 Skill content hash (`sha256-manifest-v1`)
1. For each file, compute SHA-256 over its raw bytes (no line-ending normalisation).
2. Build a manifest of lines `<hex digest><two spaces><relative path>\n`, with `/` separators.
3. Sort lines by the UTF-8 bytes of the path.
4. The skill hash is SHA-256 over the UTF-8 manifest.

The hash depends only on file paths and contents, so the same skill gives the same hash wherever it is installed. It can be reproduced with standard tools from inside the skill folder:

```sh
find . -type f ! -name .DS_Store ! -name Thumbs.db ! -name '*.pyc' \
  -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
  | sed 's|^\./||' | LC_ALL=C sort | while read -r f; do sha256sum "$f"; done | sha256sum
```

### 5.3 Aggregate hash
SHA-256 over lines `<skill hash><two spaces><skill name>\n`, sorted by the UTF-8 bytes of the name. Stored on `metadata.component`.

## 6. Signing

The profile doesn't embed signatures. Publishers SHOULD sign the BOM file with a detached, keyless attestation, for example GitHub artifact attestations (Sigstore-backed), so consumers can check it with `gh attestation verify`. Key management inside the BOM (CycloneDX JSF) is out of scope for 0.1.

## 7. Evidence (reserved for profile 0.2)

Planned, not yet emitted:

- **Eval results** as CycloneDX `declarations`: a claim per skill (e.g. guardrail adherence, obligation recall), an attestation by a named assessor, and evidence linking to the full report.
- **Binding:** each claim records the skill content hash it was produced against. A result whose hash no longer matches the skill is **stale**.
- **How it was produced** in `formulation`: harness, model and version, number of runs, date.
- **Maturity** (`experimental` / `evaluated` / `field-tested`), already passed through today as `skillbom:meta:maturity` when a skill declares it.

## 8. Conformance checks

The reference `skillbom check` applies these rules. Severity is set by policy (`error`, `warn` or `off`).

| Rule | Default | Fails when |
|---|---|---|
| `bom-profile` | error | Not CycloneDX 1.6, wrong `skillbom:profile`, or no skills |
| `skill-version` | error | A skill has no version |
| `skill-semver` | warn | A version isn't `MAJOR.MINOR.PATCH` |
| `skill-hash` | error | A skill or file lacks a valid SHA-256 |
| `skill-license` | error | A skill has no licence |
| `skill-name-matches-folder` | error | `name` differs from the folder name |
| `required-metadata` | error | A listed metadata key is missing (default: `author`) |
| `knowledge-freshness` | warn | An `as-of` date is older than `max_age_days` (default 183) |

## 9. Versioning of this profile

`skillbom:profile` changes MINOR when fields are added and MAJOR when a field changes meaning or the hash method changes. A change of hash method gets a new `skillbom:hash-method` value; existing values are never redefined.

## 10. Related work

- **CycloneDX ML-BOM / AI-BOM** and **SPDX 3.0 AI profile** describe models, datasets and services.
- **OWASP AOS AgBOM** (work in progress) describes agents, tools and their configuration.
- **cdxgen `aibom`** and other AI-BOM generators inventory prompts, models and MCP configurations.

This profile is complementary. It describes the skill as a unit of supply, including its knowledge provenance, and is intended to sit alongside those documents. Feedback and alignment proposals are welcome as issues.
