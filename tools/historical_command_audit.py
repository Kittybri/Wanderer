"""Read historical Python ASTs without importing unsafe legacy runtime."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

def inspect_snapshot(root):
    root = Path(root)
    result = {"sources": {}, "prefix": {}, "slash": {}, "help_tokens": [], "cog_modules": []}
    files = sorted(root.glob("cogs/*.py")) + sorted(root.glob("*bot.py"))
    for path in files:
        data = path.read_bytes()
        relative = str(path.relative_to(root))
        result["sources"][relative] = hashlib.sha256(data).hexdigest()
        tree = ast.parse(data)
        group_names = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if isinstance(fn, ast.Attribute) and fn.attr == "Group":
                    kw = {k.arg: k.value for k in node.value.keywords}
                    if isinstance(kw.get("name"), ast.Constant):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                group_names[target.id] = kw["name"].value
                                result["slash"][kw["name"].value] = {"source": relative, "handler": "Group"}
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets):
                for handler, name, aliases in ast.literal_eval(node.value):
                    result["prefix"][name] = {"aliases": aliases, "source": relative, "handler": handler}
                result["cog_modules"].append(relative)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute) or dec.func.attr != "command":
                    continue
                kw = {k.arg: k.value for k in dec.keywords}
                if not isinstance(kw.get("name"), ast.Constant):
                    continue
                name = kw["name"].value
                receiver = ast.unparse(dec.func.value)
                if receiver == "bot":
                    result["prefix"][name] = {"aliases": ast.literal_eval(kw["aliases"]) if "aliases" in kw else [], "source": relative, "handler": node.name}
                elif receiver == "bot.tree":
                    result["slash"][name] = {"source": relative, "handler": node.name}
                elif receiver in group_names:
                    result["slash"][group_names[receiver] + " " + name] = {"source": relative, "handler": node.name}
            if "help" in node.name:
                literals = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                result["help_tokens"].extend(re.findall(r"![a-zA-Z][a-zA-Z0-9_]*", " ".join(literals)))
    result["help_tokens"] = sorted(set(result["help_tokens"]))
    return result

if __name__ == "__main__":
    print(json.dumps(inspect_snapshot(sys.argv[1]), sort_keys=True))
