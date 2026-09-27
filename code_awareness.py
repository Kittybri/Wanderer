"""Bounded source review input, using the configured GitHub integration client."""
from __future__ import annotations
import re
from pathlib import PurePosixPath

_DENIED = re.compile(r"(secret|credential|token|integration|face|\.env|\.pem|\.key|id_rsa|lock|generated|vendor|node_modules|dist/|build/)",re.I)
_SECRET = re.compile(r"(password|secret|token|api.?key|authorization|private.key|access.key|embedding|https?://|[A-Za-z0-9_+/=-]{32,})",re.I)
_LITERAL = re.compile(r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`)""")
_SOURCE_FILES = {"bot.py","self_model.py","internal_state.py","relationship_engine.py","personality.py"}

def compact_diff(files, *, max_chars=6000, max_lines=100):
    chunks = []
    lines_left = max_lines
    for item in files[:30]:
        name = str(item.get("filename",""))
        if name not in _SOURCE_FILES or _DENIED.search(name) or PurePosixPath(name).suffix not in {".py",".js",".ts"} or not re.fullmatch(r"[\w./-]{1,160}",name):
            continue
        patch = str(item.get("patch") or "")
        safe = []
        for line in patch.splitlines():
            if _SECRET.search(line) or len(line)>250:
                continue
            if line.startswith(("+","-","@"," ")):
                line = _LITERAL.sub('"<redacted>"',line)
                line = line.split("#",1)[0].split("//",1)[0]
                if not line.strip(" +-"):
                    continue
                body = line[1:].strip()
                # Structural code only: omit free-form multiline/docstring content.
                if not line.startswith("@") and not re.match(
                    r"(?:(?:async\s+)?(?:def|class|if|elif|else|return|raise|await|for|while|try|except|finally|with|import|from|pass|break|continue)\b|[\w.]+\s*=)",body):
                    continue
                if re.match(r"[\w.]+\s*=",body):
                    line = line[0] + body.split("=",1)[0] + "= <expression omitted>"
                line = re.sub(r"\b\d+(?:\.\d+)?\b","<number>",line) if not line.startswith("@") else "@@ <location omitted> @@"
                safe.append(line)
            if len(safe)>=min(30,lines_left):
                break
        if safe:
            chunks.append(name+"\n"+"\n".join(safe))
            lines_left -= len(safe)
        if lines_left<=0:
            break
    return "\n\n".join(chunks)[:max_chars]

async def latest_commit(service, repository, branch):
    if repository.lower() not in service.allowed or not service.ready:
        return None
    from urllib.parse import quote
    if not re.fullmatch(r"[\w.-]+/[\w.-]+",repository):
        return None
    data = await service.client.request("GET",
        f"https://api.github.com/repos/{repository}/commits/{quote(branch,safe='')}",
        headers={"Authorization":f"Bearer {service.token}","Accept":"application/vnd.github+json"})
    if not re.fullmatch(r"[0-9a-f]{40,64}",str(data.get("sha",""))):
        return None
    return {"sha":str(data.get("sha","")), "diff":compact_diff(data.get("files",[])),
            "own_behavior":any(str(f.get("filename","")) in {
                "bot.py","self_model.py","internal_state.py","relationship_engine.py","personality.py"
            } for f in data.get("files",[]))}
