<<<<<<< HEAD
import discord
from datetime import datetime, timezone
import config


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(time_str: str) -> int:
    """Parse a time string like '1d2h30m' into total seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = 0
    current = ""
    for char in time_str.lower():
        if char.isdigit():
            current += char
        elif char in units and current:
            total += int(current) * units[char]
            current = ""
    return total


def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h"


def embed(
    title: str = None,
    description: str = None,
    color: int = config.COLOR_PRIMARY,
    footer: str = "GDP Community Bot",
    timestamp: bool = True,
    thumbnail: str = None,
    image: str = None,
    fields: list[tuple] = None,
) -> discord.Embed:
    """Build a styled embed quickly."""
    e = discord.Embed(title=title, description=description, color=color)
    if timestamp:
        e.timestamp = datetime.now(timezone.utc)
    if footer:
        e.set_footer(text=footer)
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    if image:
        e.set_image(url=image)
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    return e


def success_embed(description: str, title: str = "✅ Succes") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_SUCCESS)


def error_embed(description: str, title: str = "❌ Eroare") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_ERROR)


def warning_embed(description: str, title: str = "⚠️ Atenție") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_WARNING)


def info_embed(description: str, title: str = "ℹ️ Info") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_INFO)
=======
import discord
from datetime import datetime, timezone
import config


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(time_str: str) -> int:
    """Parse a time string like '1d2h30m' into total seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = 0
    current = ""
    for char in time_str.lower():
        if char.isdigit():
            current += char
        elif char in units and current:
            total += int(current) * units[char]
            current = ""
    return total


def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h"


def embed(
    title: str = None,
    description: str = None,
    color: int = config.COLOR_PRIMARY,
    footer: str = "GDP Community Bot",
    timestamp: bool = True,
    thumbnail: str = None,
    image: str = None,
    fields: list[tuple] = None,
) -> discord.Embed:
    """Build a styled embed quickly."""
    e = discord.Embed(title=title, description=description, color=color)
    if timestamp:
        e.timestamp = datetime.now(timezone.utc)
    if footer:
        e.set_footer(text=footer)
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    if image:
        e.set_image(url=image)
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    return e


def success_embed(description: str, title: str = "✅ Succes") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_SUCCESS)


def error_embed(description: str, title: str = "❌ Eroare") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_ERROR)


def warning_embed(description: str, title: str = "⚠️ Atenție") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_WARNING)


def info_embed(description: str, title: str = "ℹ️ Info") -> discord.Embed:
    return embed(title=title, description=description, color=config.COLOR_INFO)
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
