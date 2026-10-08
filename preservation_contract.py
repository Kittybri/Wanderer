"""Runtime preservation contracts. Expected manifests are reviewed, never auto-updated."""
import inspect
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
CLASSES = {"PRESENT", "RENAMED", "INTENTIONALLY_REMOVED", "ACCIDENTALLY_MISSING", "UNSAFE_TO_RESTORE_AS_IS"}

def load(name):
    return json.loads((ROOT / "preservation" / name).read_text())

def inventory(bot):
    prefix = {}
    for command in bot.walk_commands():
        prefix[command.qualified_name] = {
            "aliases": sorted(command.aliases),
            "module": command.callback.__module__,
            "cog": command.cog_name,
            "group": hasattr(command, "commands"),
            "enabled": command.enabled,
        }
    slash = {}
    for command in bot.tree.walk_commands():
        callback = getattr(command, "callback", None)
        slash[command.qualified_name] = {
            "group": hasattr(command, "commands"),
            "module": callback.__module__ if callback else None,
        }
    return {"prefix": prefix, "slash": slash, "cogs": sorted(bot.cogs),
            "extensions": sorted(bot.extensions),
            "listeners": {event: sorted(f.__module__ + "." + f.__qualname__ for f in callbacks)
                          for event, callbacks in bot.extra_events.items()}}

def resolve(module, path):
    value = module
    for part in path.split("."):
        value = getattr(value, part)
    return value

def validate(module, help_text, commands=None, features=None):
    commands = commands or load("commands.json")
    features = features or load("features.json")
    actual = inventory(module.bot)
    errors = []
    for path, expected in features.get("components", {}).items():
        try:
            obj = resolve(module, path)
            if [type(obj).__module__, type(obj).__name__] != expected:
                errors.append(f"changed component: {path}")
        except AttributeError:
            errors.append(f"missing component: {path}")
    for kind in ("prefix", "slash"):
        for name, expected in commands[kind].items():
            found = actual[kind].get(name)
            if found is None:
                errors.append(f"missing {kind}: {name}")
                continue
            for key in ("aliases", "module", "cog", "group"):
                if key in expected and expected[key] != found.get(key):
                    errors.append(f"{kind} {name}: changed {key}")
            if kind == "prefix" and not found["enabled"]:
                errors.append(f"disabled prefix: {name}")
            if kind == "prefix":
                command = module.bot.get_command(name)
                parent = name.rsplit(" ", 1)[0] + " " if " " in name else ""
                for alias in expected.get("aliases", []):
                    if module.bot.get_command(parent + alias) is not command:
                        errors.append(f"missing alias: {parent + alias}")
            mod = found.get("module")
            if mod and mod not in sys.modules:
                errors.append(f"unloaded module: {mod}")
    for key in ("cogs", "extensions"):
        if not set(commands[key]) <= set(actual[key]):
            errors.append(f"missing {key}")
    for event, callbacks in commands.get("listeners", {}).items():
        if not set(callbacks) <= set(actual["listeners"].get(event, [])):
            errors.append(f"missing listener: {event}")
    for entry in commands["help_entries"]:
        if not re.search(re.escape(entry) + r"(?![\w])", help_text):
            errors.append(f"missing help: {entry}")
    for family, spec in features["features"].items():
        if spec["status"] != "PRESENT":
            continue
        if not spec.get("prefix") and not spec.get("wiring"):
            errors.append(f"unproven feature: {family}")
        for name in spec.get("prefix", []):
            if name not in actual["prefix"]:
                errors.append(f"feature {family}: missing {name}")
        for path in spec.get("wiring", []):
            try:
                obj = resolve(module, path)
                if obj is None:
                    raise AttributeError(path)
                if path in spec.get("callable", []) and not callable(obj):
                    raise AttributeError(path)
            except AttributeError:
                errors.append(f"feature {family}: unwired {path}")
        for stage in spec.get("privacy_stages", []):
            if not callable(module.PRIVACY_DELETION.stages.get(stage)):
                errors.append(f"feature {family}: missing privacy stage {stage}")
    return errors

def removal_errors(before, after, changes):
    """CI diff gate: manifest deletions require an explicit reviewed authorization record."""
    removed = set()
    for kind in ("prefix", "slash"):
        removed |= {f"{kind}:{name}" for name in set(before.get(kind, {})) - set(after.get(kind, {}))}
        for name, spec in before.get(kind, {}).items():
            for alias in set(spec.get("aliases", [])) - set(after.get(kind, {}).get(name, {}).get("aliases", [])):
                removed.add(f"alias:{name}:{alias}")
    removed |= {"help:" + v for v in set(before.get("help_entries", [])) - set(after.get("help_entries", []))}
    for family, spec in before.get("features", {}).items():
        if spec.get("status") == "PRESENT" and after.get("features", {}).get(family, {}).get("status") != "PRESENT":
            removed.add("feature:" + family)
        for key in ("prefix", "wiring", "callable", "privacy_stages"):
            for value in set(spec.get(key, [])) - set(after.get("features", {}).get(family, {}).get(key, [])):
                removed.add(f"feature:{family}:{key}:{value}")
    for key in ("cogs", "extensions", "owner_commands"):
        removed |= {f"{key}:{v}" for v in set(before.get(key, [])) - set(after.get(key, []))}
    for event, callbacks in before.get("listeners", {}).items():
        removed |= {f"listener:{event}:{v}" for v in set(callbacks) - set(after.get("listeners", {}).get(event, []))}
    expected_unresolved = {(r["surface"], r["name"]) for r in before.get("unresolved_surfaces", [])}
    retained = {(r["surface"], r["name"]) for r in after.get("unresolved_surfaces", [])}
    # Resolving an omission is valid; silently forgetting it is not.
    for surface, name in expected_unresolved - retained:
        kind = "slash" if surface == "slash" else "prefix"
        if name.lstrip("!") not in after.get(kind, {}):
            removed.add(f"unresolved:{surface}:{name}")
    allowed = set()
    for record in changes:
        if all(record.get(key) for key in ("authorization", "reason", "replacement", "privacy_impact", "validation")):
            allowed.update(record.get("removed_surfaces", []))
    return sorted(removed - allowed)
