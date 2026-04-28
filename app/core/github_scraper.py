import re
from datetime import date

import httpx


def _parse_tooltip_count(tooltip_text: str) -> int:
    if "No contributions" in tooltip_text:
        return 0
    match = re.search(r"([\d,]+)\s+contributions?", tooltip_text, re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def fetch_contribution_cells_for_year(
    client: httpx.Client, github_username: str, year: int
) -> dict[date, int]:
    """Scrapes GitHub contribution graph for a year. Returns {date: contribution_count}."""
    resp = client.get(
        f"https://github.com/users/{github_username}/contributions?from={year}-01-01&to={year}-12-31",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        return {}

    html = resp.text

    date_by_component_id: dict[str, date] = {}
    for m in re.finditer(
        r'<td[^>]*data-date="([0-9]{4}-[0-9]{2}-[0-9]{2})"[^>]*id="(contribution-day-component-[^"]+)"|'
        r'<td[^>]*id="(contribution-day-component-[^"]+)"[^>]*data-date="([0-9]{4}-[0-9]{2}-[0-9]{2})"',
        html,
    ):
        cell_date = m.group(1) or m.group(4)
        component_id = m.group(2) or m.group(3)
        if cell_date and component_id:
            date_by_component_id[component_id] = date.fromisoformat(cell_date)

    tooltip_count_by_component_id = {
        component_id: _parse_tooltip_count(re.sub(r"\s+", " ", tooltip_text.strip()))
        for component_id, tooltip_text in re.findall(
            r'<tool-tip[^>]*for="(contribution-day-component-[^"]+)"[^>]*>(.*?)</tool-tip>',
            html,
            re.S,
        )
    }

    return {
        cell_date: tooltip_count_by_component_id.get(component_id, 0)
        for component_id, cell_date in date_by_component_id.items()
    }


def fetch_available_contribution_years(
    client: httpx.Client, github_username: str
) -> list[int]:
    from datetime import datetime, timezone

    resp = client.get(
        f"https://github.com/users/{github_username}/contributions",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        return [datetime.now(timezone.utc).year]

    years = sorted(
        {int(y) for y in re.findall(r'id="year-link-(\d{4})"', resp.text)},
        reverse=True,
    )
    return years or [datetime.now(timezone.utc).year]
