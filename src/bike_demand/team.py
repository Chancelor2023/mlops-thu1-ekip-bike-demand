
import re


def normalize_team_slug(team_name: str) -> str:
    cleaned = team_name.strip()
    if not cleaned:
        raise ValueError("Team name must contain non-whitespace characters")
    return re.sub(r"\s+", "-", cleaned).lower()
