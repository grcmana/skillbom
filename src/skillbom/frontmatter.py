"""Minimal, deterministic YAML-frontmatter reader (stdlib only).

Supports the subset used by Agent Skills SKILL.md files and knowledge packs:
scalars, single/double-quoted strings, nested mappings by indentation,
flow lists ``[a, b]``, block lists ``- item`` and block scalars ``|`` / ``>``.
All scalar values are returned as strings; this tool never coerces types,
so ``version: 0.1.0`` and ``version: "0.1.0"`` read the same.

Anything outside this subset raises ``FrontmatterError`` rather than guessing.
"""
from __future__ import annotations

from typing import Any

__all__ = ["FrontmatterError", "split", "parse"]


class FrontmatterError(ValueError):
    pass


def split(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_text, body). frontmatter_text is None if absent."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    raise FrontmatterError("frontmatter opened with '---' but never closed")


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        inner = v[1:-1]
        return (inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\"))
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    # strip trailing comment on plain scalars
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def _flow_list(v: str) -> list[str]:
    inner = v.strip()[1:-1].strip()
    if not inner:
        return []
    out, buf, q = [], "", None
    for ch in inner:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch == ",":
            out.append(_unquote(buf))
            buf = ""
        else:
            buf += ch
    out.append(_unquote(buf))
    return out


def _indent(line: str) -> int:
    if "\t" in line[: len(line) - len(line.lstrip())]:
        raise FrontmatterError("tabs are not allowed for indentation")
    return len(line) - len(line.lstrip(" "))


def parse(fm: str) -> dict[str, Any]:
    lines = [ln.rstrip() for ln in fm.splitlines()]
    pos = 0

    def skip_blank() -> None:
        nonlocal pos
        while pos < len(lines) and (not lines[pos].strip() or lines[pos].lstrip().startswith("#")):
            pos += 1

    def block_scalar(style: str, parent_indent: int) -> str:
        nonlocal pos
        collected: list[str] = []
        ind = None
        while pos < len(lines):
            ln = lines[pos]
            if ln.strip() and _indent(ln) <= parent_indent:
                break
            if ln.strip() and ind is None:
                ind = _indent(ln)
            collected.append(ln[ind:] if ind is not None and ln.strip() else "")
            pos += 1
        while collected and not collected[-1]:
            collected.pop()
        if style.startswith("|"):
            return "\n".join(collected)
        # folded: join non-empty runs with spaces, blank lines become newlines
        out, para = [], []
        for c in collected:
            if c:
                para.append(c.strip())
            else:
                out.append(" ".join(para))
                para = []
        out.append(" ".join(para))
        return "\n".join(p for p in out)

    def parse_value(rest: str, indent: int) -> Any:
        nonlocal pos
        rest = rest.strip()
        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            return block_scalar(rest, indent)
        if rest.startswith("[") and rest.endswith("]"):
            return _flow_list(rest)
        if rest.startswith("{"):
            raise FrontmatterError("flow mappings are not supported")
        if rest:
            return _unquote(rest)
        # nested block
        skip_blank()
        if pos >= len(lines) or _indent(lines[pos]) <= indent:
            return ""
        child = _indent(lines[pos])
        if lines[pos].lstrip().startswith("- "):
            return parse_list(child)
        return parse_map(child)

    def parse_list(indent: int) -> list[Any]:
        nonlocal pos
        items: list[Any] = []
        while True:
            skip_blank()
            if pos >= len(lines) or _indent(lines[pos]) != indent:
                break
            s = lines[pos].strip()
            if not s.startswith("- ") and s != "-":
                break
            pos += 1
            item = s[1:].strip()
            if ":" in item and not item.startswith(("'", '"')):
                raise FrontmatterError("lists of mappings are not supported")
            items.append(_unquote(item))
        return items

    def parse_map(indent: int) -> dict[str, Any]:
        nonlocal pos
        out: dict[str, Any] = {}
        while True:
            skip_blank()
            if pos >= len(lines):
                break
            ln = lines[pos]
            ind = _indent(ln)
            if ind < indent:
                break
            if ind > indent:
                raise FrontmatterError(f"unexpected indentation at line {pos + 1}")
            s = ln.strip()
            if ":" not in s:
                raise FrontmatterError(f"expected 'key: value' at line {pos + 1}")
            key, rest = s.split(":", 1)
            key = _unquote(key)
            if key in out:
                raise FrontmatterError(f"duplicate key '{key}'")
            pos += 1
            out[key] = parse_value(rest, indent)
        return out

    result = parse_map(0)
    skip_blank()
    if pos < len(lines):
        raise FrontmatterError(f"could not parse line {pos + 1}: {lines[pos]!r}")
    return result


def read(text: str) -> tuple[dict[str, Any], str]:
    fm, body = split(text)
    return (parse(fm) if fm is not None else {}), body
