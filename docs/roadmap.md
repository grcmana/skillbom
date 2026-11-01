# Roadmap

SkillBOM is experimental. This is the intended direction, not a commitment to dates. Suggestions are welcome as issues; changes to the profile start with a [profile proposal](https://github.com/grcmana/skillbom/issues/new?template=profile.yml).

## Now: v0.0.x
- [x] Skill BOM profile 0.1 for CycloneDX 1.6
- [x] `generate`, `check`, `verify`
- [x] Signed releases (GitHub artifact attestations)
- [x] Worked example: GRC Skills v0.1.0
- [ ] First adopter: GRC Skills attaches a signed `skillbom.cdx.json` to every release

## Next: profile 0.2, evidence
- Record test results against a skill as CycloneDX `declarations` (claims, evidence, assessor), with how they were produced in `formulation` (harness, model, number of runs).
- Bind every result to the skill fingerprint it ran against.
- New `check` rule: flag evidence whose fingerprint no longer matches the skill (stale results).
- Pass through a maturity label (`experimental` / `evaluated` / `field-tested`) as a first-class field.
- First source of evidence: [GRC Evals](https://grcevals.io).

## Later
- Publish to PyPI with trusted publishing, so `pip install skillbom` works.
- A portable signature bundle (`cosign`) for people who don't use GitHub.
- A hash method that also covers file permissions.
- `verify` that can fetch and check a release's signed BOM in one step, as an explicit opt-in.
- Register the `skillbom:` property namespace in the CycloneDX property taxonomy.
- Work with OWASP's Agent BOM effort and other AI-BOM projects so a Skill BOM can sit inside a wider agent BOM.

## Not planned
- Scoring or ranking skills. SkillBOM records evidence; it doesn't judge it.
- Any LLM in `generate`, `check` or `verify`.
- A hosted service. Everything works from files.
