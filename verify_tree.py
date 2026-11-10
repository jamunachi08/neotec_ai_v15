#!/usr/bin/env python3
"""Structural guard for neotec_ai. Run before every push: python verify_tree.py"""

import ast
import base64
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
APP = ROOT / "neotec_ai"
MODS = {"Neotec AI": APP / "neotec_ai", "Neotec AI Agents": APP / "neotec_ai_agents"}
MOD = MODS["Neotec AI Agents"]
AGENTS = APP / "agents"
CORE_DOCTYPES = {"User", "Role", "DocType", "Notification Log", "File", "Has Role", "Report", "Module Def",
                 "Company", "Email Account", "Workflow", "Print Format", "Dashboard Chart", "Number Card"}
# Names of reviewed third-party products and other brands that must never ship (kept encoded).
BANNED = re.compile(r"(?i)\b(" + base64.b64decode("b3BlbmJvdHxjb3BpbG90a2l0fGFnbm98YWdlbnRvc3xzdHJhbmRzfGEydWl8YWctdWl8bGFuZ2dyYXBofGNyZXdhaXxhbHBoYXh8YWVvbnxvcGVuZGlhfGtpbWl8cm93Ym9hdHxmcmVlbGxtYXBpfG1vb25zaG90").decode() + r")\b")
errors = []


def err(msg):
    errors.append(msg)


def scrub(s):
    return s.lower().replace(" ", "_").replace("-", "_")


# 1. required files
for rel in ["pyproject.toml", "README.md", "CHANGELOG.md", "license.txt", "neotec_ai/__init__.py",
            "neotec_ai/hooks.py", "neotec_ai/modules.txt", "neotec_ai/patches.txt",
            "neotec_ai/public/css/coworker.css", "neotec_ai/public/js/coworker_launcher.js",
            "neotec_ai/public/images/logo.svg", "neotec_ai/public/js/coworker_models.js",
            "neotec_ai/public/js/neotec_writing.js", "neotec_ai/public/js/neotec_ai.js", "neotec_ai/public/js/neotec_bi.js",
            "docs/OPEN_MODELS.md", "docs/PLATFORM.md", "docs/MIGRATION.md", "deploy/gpu-server/docker-compose.yml", "deploy/gpu-server/Caddyfile",
            "deploy/gpu-server/.env.example", "deploy/gpu-server/README.md"]:
    if not (ROOT / rel).exists():
        err(f"missing {rel}")

if (APP / "modules.txt").read_text().strip().splitlines() != list(MODS):
    err("modules.txt must list exactly: " + ", ".join(MODS))

# 2. doctypes
names = set()
links = []
for folder, MODULE in sorted(((f, m) for m, d in MODS.items() for f in (d / "doctype").iterdir()),
                            key=lambda x: x[0].name):
    if not folder.is_dir() or folder.name.startswith("__"):
        continue
    js = folder / f"{folder.name}.json"
    py = folder / f"{folder.name}.py"
    for f in (js, py, folder / "__init__.py"):
        if not f.exists():
            err(f"{folder.name}: missing {f.name}")
    if not js.exists():
        continue
    d = json.loads(js.read_text())
    names.add(d["name"])
    if scrub(d["name"]) != folder.name:
        err(f"{folder.name}: name {d['name']} does not match folder")
    if d.get("module") != MODULE:
        err(f"{d['name']}: module is {d.get('module')}")
    fns = [f["fieldname"] for f in d["fields"]]
    if len(fns) != len(set(fns)):
        err(f"{d['name']}: duplicate fieldnames")
    if d.get("field_order") != fns:
        err(f"{d['name']}: field_order out of sync")
    if d.get("title_field") and d["title_field"] not in fns:
        err(f"{d['name']}: title_field {d['title_field']} missing")
    an = d.get("autoname", "")
    if an.startswith("field:") and an[6:] not in fns:
        err(f"{d['name']}: autoname field missing")
    for f in d["fields"]:
        if f["fieldtype"] in ("Link", "Table") and f.get("options"):
            links.append((d["name"], f["fieldname"], f["options"]))
        if f["fieldtype"] == "Dynamic Link" and f.get("options") not in fns:
            err(f"{d['name']}.{f['fieldname']}: dynamic link source missing")
    if py.exists():
        cls = d["name"].replace(" ", "").replace("-", "")
        tree = ast.parse(py.read_text())
        if cls not in [n.name for n in tree.body if isinstance(n, ast.ClassDef)]:
            err(f"{d['name']}: controller class {cls} not found")
for dt, field, target in links:
    if target not in names and target not in CORE_DOCTYPES:
        err(f"{dt}.{field}: link target {target} unknown")

# 3. pages and workspace
pages = set()
for mod_dir, page in ((MOD, "coworker"), (MOD, "coworker_setup"), (MOD, "coworker_health"),
                      (MODS["Neotec AI"], "neotec_bi"), (MODS["Neotec AI"], "neotec_dashboard")):
    for ext in ("json", "js"):
        if not (mod_dir / "page" / page / f"{page}.{ext}").exists():
            err(f"page {page}: missing .{ext}")
    if (mod_dir / "page" / page / f"{page}.json").exists():
        pages.add(json.loads((mod_dir / "page" / page / f"{page}.json").read_text())["name"])
for ws in (MOD / "workspace" / "ai_coworkers" / "ai_coworkers.json",
           MODS["Neotec AI"] / "workspace" / "neotec_ai" / "neotec_ai.json"):
    if not ws.exists():
        err(f"workspace missing: {ws.name}")
        continue
    w = json.loads(ws.read_text())
    for l in w["links"]:
        if l["type"] == "Link" and l["link_to"] not in names and l["link_to"] not in pages:
            err(f"{ws.name}: link to unknown {l['link_to']}")

# 4. hooks resolve to real functions
hooks = ast.parse((APP / "hooks.py").read_text())
dotted = set()
for node in ast.walk(hooks):
    if isinstance(node, ast.Constant) and isinstance(node.value, str) \
            and node.value.startswith("neotec_ai.") and "/" not in node.value:
        dotted.add(node.value)
for path in sorted(dotted):
    mod, fn = path.rsplit(".", 1)
    f = ROOT / (mod.replace(".", "/") + ".py")
    if not f.exists():
        err(f"hook {path}: module file missing")
        continue
    if fn not in {n.name for n in ast.parse(f.read_text()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}:
        err(f"hook {path}: function missing")

# 5. every python file compiles; no stray third-party product names; version consistent
for f in ROOT.rglob("*"):
    if f.is_dir() or "node_modules" in f.parts or "__pycache__" in f.parts or f.name == "verify_tree.py":
        continue
    if f.suffix == ".py":
        try:
            compile(f.read_text(), str(f), "exec")
        except SyntaxError as e:
            err(f"{f}: {e}")
    if f.suffix in (".py", ".js", ".json", ".md", ".css", ".csv", ".txt", ".toml"):
        # field_meanings.py lists real custom field names of connected apps so the Data Dictionary can explain them.
        m = None if f.name == "field_meanings.py" else BANNED.search(f.read_text(errors="ignore"))
        if m:
            err(f"{f.relative_to(ROOT)}: contains '{m.group(0)}'")

version = re.search(r'__version__ = "([^"]+)"', (APP / "__init__.py").read_text()).group(1)
if f"## {version}" not in (ROOT / "CHANGELOG.md").read_text():
    err(f"CHANGELOG has no entry for {version}")

# 6. every seeded tool exists in code
reg = set(re.findall(r'@tool\("([a-z0-9_]+)"', "".join(p.read_text() for p in (AGENTS / "tools").glob("*.py"))))
seed = (AGENTS / "setup" / "seed.py").read_text()
v4 = (APP / "platform" / "setup.py").read_text().split("V4_GRANTS = {")[1].split("\n}\n")[0]
for t in set(re.findall(r'"([a-z_]+)": "(?:Default|Ask|Auto|Off)"', v4)):
    if t not in reg:
        err(f"4.0 grants unknown tool {t}")
for t in set(re.findall(r'"([a-z_]+)": "(?:Default|Ask|Auto|Off)"', seed)) | set(re.findall(r'"([a-z_]+)"', seed.split("READ_CORE = [")[1].split("]")[0])):
    if t not in reg:
        err(f"seed grants unknown tool {t}")

# 7. starter packs: every playbook's tools exist and are granted to its coworker; chains/triggers resolve
tree = ast.parse(seed)
ns = {}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.Assign)
                              and any(getattr(t, "id", "") in ("READ_CORE", "COWORKERS") for t in n.targets)],
                        type_ignores=[]), "seed", "exec"), ns)
grants = {name: set(spec[-1]) for name, spec in ns["COWORKERS"].items()}
pb_ns = {}
exec((AGENTS / "setup" / "playbooks.py").read_text(), pb_ns)
for name, p in pb_ns["PLAYBOOKS"].items():
    if p["pack"] not in pb_ns["PACKS"]:
        err(f"playbook {name}: unknown pack {p['pack']}")
    if p["coworker"] not in grants:
        err(f"playbook {name}: unknown coworker {p['coworker']}")
        continue
    for t in re.split(r"[\s,]+", p["required_tools"].strip()):
        if t not in reg:
            err(f"playbook {name}: tool {t} does not exist")
        elif t not in grants[p["coworker"]]:
            err(f"playbook {name}: {p['coworker']} is not granted {t}")
    for key in re.findall(r"\{([a-z_]+)\}", p["instructions"]):
        if key not in ("parameter", "today"):
            err(f"playbook {name}: unknown placeholder {{{key}}}")
    if "{parameter}" in p["instructions"] and not p.get("parameter_label"):
        err(f"playbook {name}: uses {{parameter}} but has no parameter label")
for name, c in pb_ns["CHAINS"].items():
    for step in c["steps"]:
        if step[0] not in pb_ns["PLAYBOOKS"]:
            err(f"chain {name}: unknown playbook {step[0]}")
for name, t in pb_ns["TRIGGERS"].items():
    if t["playbook"] not in pb_ns["PLAYBOOKS"]:
        err(f"trigger {name}: unknown playbook {t['playbook']}")

# 7b. open-model catalogue: valid tiers, compilable patterns, every model recognises its own Hugging Face id
om_ns = {}
exec((AGENTS / "setup" / "open_models.py").read_text(), om_ns)
keys = set()
for m in om_ns["MODELS"]:
    if m["key"] in keys:
        err(f"open model {m['key']}: duplicate key")
    keys.add(m["key"])
    if m["tier"] not in om_ns["TIERS"]:
        err(f"open model {m['key']}: unknown tier {m['tier']}")
    for pat in m["match"]:
        try:
            re.compile(pat)
        except re.error as e:
            err(f"open model {m['key']}: bad pattern {pat}: {e}")
    if m["hf_id"] and om_ns["match_catalogue"](m["hf_id"]) is not m:
        err(f"open model {m['key']}: its Hugging Face id is matched by another entry")

# 7c. every provider preset offered in the wizard is a valid Select option on Coworker Provider
api_src = (AGENTS / "api.py").read_text()
presets = re.findall(r'^    "([^"]+)": \{', api_src.split("PRESETS = {")[1].split("\n}\n")[0], re.M)
prov = json.loads((MOD / "doctype" / "coworker_provider" / "coworker_provider.json").read_text())
options = next(f["options"] for f in prov["fields"] if f["fieldname"] == "preset").split("\n")
for p in presets:
    if p not in options:
        err(f"preset {p} is not an option of Coworker Provider.preset")

# 8. patches resolve
for line in (APP / "patches.txt").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("[") or line.startswith("#"):
        continue
    f = ROOT / (line.replace(".", "/") + ".py")
    if not f.exists() or "execute" not in {n.name for n in ast.parse(f.read_text()).body if isinstance(n, ast.FunctionDef)}:
        err(f"patch {line}: missing file or execute()")

if errors:
    print("verify_tree: FAILED")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"verify_tree: OK  ({len(names)} doctypes, {len(reg)} tools, {len(pb_ns['PLAYBOOKS'])} playbooks, "
      f"{len(om_ns['MODELS'])} open models, {len(presets)} presets, version {version})")
