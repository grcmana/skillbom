# Contributing

Thanks for helping. SkillBOM is small on purpose, so please open an issue before a large change.

## Principles
1. **Don't invent a format.** Use standard CycloneDX fields first; `skillbom:` properties only where none fits.
2. **Deterministic.** Same input, same bytes out. No network, no clock (except `SOURCE_DATE_EPOCH`), no LLM.
3. **No runtime dependencies.** Python standard library only. Test-only dependencies are fine.
4. **Fail closed.** If input can't be described accurately (e.g. a symlink, unparseable frontmatter), stop with a clear error rather than guess.

## Changes to the profile
Changes to `SPEC.md` need an issue first. Adding a field is a MINOR profile change; changing a field's meaning or the hash method is MAJOR. Never redefine an existing `skillbom:hash-method` value.

## Development
```sh
pip install "cyclonedx-python-lib[json-validation]>=8"   # schema validation in tests
PYTHONPATH=src python -m unittest discover -s tests -v
```

If your change alters the output, regenerate the worked example and include it in the PR:

```sh
git clone --depth 1 --branch v0.1.0 https://github.com/grcmana/grcskills /tmp/grcskills
SOURCE_DATE_EPOCH=$(git -C /tmp/grcskills log -1 --format=%ct) PYTHONPATH=src python -m skillbom generate /tmp/grcskills \
  --name grcskills --version v0.1.0 --repo-url https://github.com/grcmana/grcskills \
  -o examples/grcskills-v0.1.0.cdx.json
```

## Pull requests
- One change per PR, with a test.
- CI must pass. A maintainer review is required to merge.
- By contributing you agree your code is licensed under Apache-2.0 and spec text under CC-BY-4.0.
- Please follow the [code of conduct](CODE_OF_CONDUCT.md).
