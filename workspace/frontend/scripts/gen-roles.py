#!/usr/bin/env python3
"""Generate lib/role-templates.data.ts from VoltAgent/awesome-claude-code-subagents.

Usage:
  git clone --depth 1 https://github.com/VoltAgent/awesome-claude-code-subagents /tmp/awesome-claude-code-subagents
  python3 scripts/gen-roles.py /tmp/awesome-claude-code-subagents/categories
"""
import json, os, re, glob

import sys
SRC = sys.argv[1] if len(sys.argv) > 1 else "/tmp/awesome-claude-code-subagents/categories"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "lib", "role-templates.data.ts")

ACRONYMS = {"api","ai","ml","ui","ux","qa","sql","css","html","ios","sre","devops",
            "graphql","nlp","llm","ci","cd","aws","gcp","ci/cd","cli","sdk","seo",
            "iot","ar","vr","3d","ocr","etl","mlops","devsecops","wordpress","php",
            "macos","tui","saas","crm","erp","b2b","pwa"}

def humanize(slug: str) -> str:
    parts = slug.split("-")
    out = []
    for p in parts:
        out.append(p.upper() if p.lower() in ACRONYMS else p.capitalize())
    return " ".join(out)

def cat_id(dirname: str) -> str:
    return re.sub(r"^\d+-", "", dirname)

def parse_frontmatter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fm = {}
    for line in fm_raw.splitlines():
        mm = re.match(r"^(\w+):\s*(.*)$", line)
        if mm:
            v = mm.group(2).strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            fm[mm.group(1)] = v
    return fm, body

def first_sentence(s: str) -> str:
    s = s.strip()
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return (m.group(1) if m else s).strip()

def make_tagline(body: str, desc: str) -> str:
    # Prefer the persona intro: "You are a ... specializing in X."
    intro = ""
    for para in body.split("\n\n"):
        p = para.strip()
        if p:
            intro = p
            break
    sent = first_sentence(intro) if intro else ""
    tag = ""
    m = re.search(r"specializing in (.+)", sent, re.I)
    if m:
        tag = m.group(1)
    else:
        m = re.search(r"with expertise in (.+)", sent, re.I)
        if m:
            tag = m.group(1)
    if not tag:
        d = re.sub(r"^use this agent (when|for)\s+", "", desc.strip(), flags=re.I)
        tag = first_sentence(d)
    tag = tag.strip().rstrip(".")
    if tag:
        tag = tag[0].upper() + tag[1:]
    if len(tag) > 130:
        tag = tag[:127].rstrip() + "..."
    return tag

HEADER_RE = re.compile(r"^([A-Z][A-Za-z0-9 /+&.-]{2,40}):\s*$")
SKIP_HEADERS = ("when invoked", "communication protocol", "workflow",
                "integration", "deliverables", "best practices", "always ",
                "use these", "each ", "subagent", "this ", "the ")

def extract_skills_abilities(body: str):
    lines = body.splitlines()
    headers = []           # (index, label)
    for i, ln in enumerate(lines):
        m = HEADER_RE.match(ln.strip())
        if not m:
            continue
        label = m.group(1).strip()
        low = label.lower()
        if any(low.startswith(s) or s in low for s in SKIP_HEADERS):
            continue
        headers.append((i, label))
    # skills = first ~6 themed section labels, trimmed
    skills = []
    for _, label in headers:
        s = re.sub(r"\b(checklist|approach|strategies|principles|patterns)\b\s*$", "", label, flags=re.I).strip()
        s = label if not s else s
        if len(s) > 26:
            s = s[:24].rstrip() + "…"
        if s not in skills:
            skills.append(s)
        if len(skills) >= 6:
            break
    # abilities = first 3 bullets under the first themed section
    abilities = []
    if headers:
        start = headers[0][0] + 1
        for ln in lines[start:start+12]:
            t = ln.strip()
            if t.startswith("- "):
                b = t[2:].strip().rstrip(".")
                if b:
                    abilities.append(b[0].upper() + b[1:])
            elif t and not t.startswith("- ") and abilities:
                break
            if len(abilities) >= 3:
                break
    # fallback abilities: "When invoked" numbered steps
    if not abilities:
        for ln in lines:
            m = re.match(r"^\d+\.\s+(.*)$", ln.strip())
            if m:
                b = m.group(1).strip().rstrip(".")
                abilities.append(b[0].upper() + b[1:])
            if len(abilities) >= 3:
                break
    return skills, abilities

def map_model(m: str) -> str:
    # VoltAgent uses Claude tiers (sonnet/opus/haiku) — all Claude runtime.
    return "claude"

roles = []
for d in sorted(os.listdir(SRC)):
    dpath = os.path.join(SRC, d)
    if not os.path.isdir(dpath):
        continue
    cid = cat_id(d)
    for f in sorted(glob.glob(os.path.join(dpath, "*.md"))):
        if os.path.basename(f).lower() == "readme.md":
            continue
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        fm, body = parse_frontmatter(text)
        if not fm.get("name"):   # skip non-agent files (no frontmatter)
            continue
        name_slug = fm.get("name")
        tagline = make_tagline(body, fm.get("description", ""))
        skills, abilities = extract_skills_abilities(body)
        roles.append({
            "id": name_slug,
            "name": humanize(name_slug),
            "cat": cid,
            "model": map_model(fm.get("model", "")),
            "tagline": tagline,
            "skills": skills,
            "abilities": abilities,
        })

header = (
    "/* AUTO-GENERATED from VoltAgent/awesome-claude-code-subagents "
    f"({len(roles)} roles, 10 categories).\n"
    "   Regenerate with scripts/gen-roles.py — do not edit by hand. */\n"
    "import type { RoleTemplate } from './role-templates';\n\n"
    "export const ROLE_TEMPLATES: RoleTemplate[] = "
)
with open(OUT, "w", encoding="utf-8") as out:
    out.write(header + json.dumps(roles, indent=2, ensure_ascii=False) + ";\n")

print(f"wrote {len(roles)} roles to {OUT}")
cats = {}
for r in roles:
    cats[r["cat"]] = cats.get(r["cat"], 0) + 1
for c, n in cats.items():
    print(f"  {c}: {n}")
