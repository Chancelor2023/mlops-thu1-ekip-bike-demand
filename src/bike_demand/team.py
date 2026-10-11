
import re


def normalize_team_slug(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Team name must contain non-whitespace characters")
    return re.sub(r"\s+", "-", cleaned).lower()
