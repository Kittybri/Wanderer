"""Deliver growing help menus within Discord's embed/message limits."""
from __future__ import annotations

import discord
from copy import deepcopy


def paginate_help(pages):
    """Preserve every entry; split fields and enforce the 6,000-character limit."""
    result = []
    for source in pages:
        base = deepcopy(source)
        base.clear_fields()
        if (len(base) > 6000 or len(base.title or "") > 256
                or len(base.description or "") > 4096
                or len(base.footer.text or "") > 2048
                or len(base.author.name or "") > 256):
            raise ValueError("Help metadata requires plain-text delivery")
        page = deepcopy(base)
        for field in source.fields:
            name = field.name or "\u200b"
            value = field.value or "\u200b"
            if len(name) > 256 or len(value) > 1024:
                raise ValueError("Help field requires plain-text delivery")
            size = len(name) + len(value)
            if len(base) + size > 6000:
                raise ValueError("Help entry requires plain-text delivery")
            if len(page.fields) >= 25 or len(page) + size > 6000:
                result.append(page)
                page = deepcopy(base)
            page.add_field(name=name, value=value, inline=field.inline)
        result.append(page)
    return result


def embed_batches(pages):
    batch = []
    size = 0
    for page in pages:
        if batch and (len(batch) >= 10 or size + len(page) > 6000):
            yield batch
            batch, size = [], 0
        batch.append(page)
        size += len(page)
    if batch:
        yield batch


def plaintext_chunks(pages, limit=1900):
    """No [:1900] truncation: preserve the end of long help pages too."""
    text = "\n\n".join(
        "\n".join(filter(None, [
            f"**{page.title}**" if page.title else "",
            page.description,
            *(f"{field.name} — {field.value}" for field in page.fields),
            page.footer.text,
        ])) for page in pages
    )
    while text:
        cut = min(limit, len(text))
        if len(text) > limit:
            boundary = text.rfind("\n", 0, limit)
            if boundary > 0:
                cut = boundary + 1
        yield text[:cut]
        text = text[cut:]


async def send_help_plaintext(ctx, pages):
    for chunk in plaintext_chunks(pages):
        await ctx.send(chunk, allowed_mentions=discord.AllowedMentions.none())


async def send_help(ctx, pages):
    try:
        batches = list(embed_batches(paginate_help(pages)))
    except ValueError:
        await send_help_plaintext(ctx, pages)
        return
    for index, batch in enumerate(batches):
        try:
            await ctx.send(embeds=batch, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            # Do not repeat batches already delivered if a later send fails.
            await send_help_plaintext(ctx, [p for rest in batches[index:] for p in rest])
            return
