"""Build index.html for NBA Tonight.

Pulls the next 7 days of NBA games from ESPN's public scoreboard feed,
sorts each game onto the service that carries it (Prime Video, Peacock,
ESPN, or League Pass) and writes the data into template.html.

Injury lists refresh once a day, at the first build after 6:30 PM Eastern.
Every other build reuses the injury lists from the live page, passed with
--prev (the page's saved HTML). Without --prev, injuries are fetched fresh.

Usage: python3 build.py [--prev PATH_TO_LIVE_PAGE_HTML]
"""
import argparse
import json
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
FEED = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={}"
ROSTER = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/roster"
DAYS = 7
INJURY_REFRESH = (18, 30)  # 6:30 PM Eastern
HERE = Path(__file__).parent

# National broadcast name (as ESPN lists it) -> service.
# NBC and NBCSN games stream on Peacock; ABC games stream on ESPN.
SERVICE_OF = {
    "prime video": "prime",
    "peacock": "peacock",
    "nbc": "peacock",
    "nbcsn": "peacock",
    "espn": "espn",
    "espn2": "espn",
    "abc": "espn",
}


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def fetch_day(day):
    return get_json(FEED.format(day.strftime("%Y%m%d")))


def salary(athlete, season_year):
    """This season's salary, or the latest one listed; 0 when unknown."""
    contracts = athlete.get("contracts") or []
    for c in contracts:
        if c.get("season", {}).get("year") == season_year:
            return c.get("salary") or 0
    return max((c.get("salary") or 0 for c in contracts), default=0)


def team_status(team_id):
    """Roster size and the players listed as Out, highest paid first."""
    data = get_json(ROSTER.format(team_id))
    season_year = data.get("season", {}).get("year")
    athletes = data.get("athletes", [])
    out = [
        a for a in athletes
        if any((i.get("status") or "").lower() == "out" for i in a.get("injuries") or [])
    ]
    out.sort(key=lambda a: salary(a, season_year), reverse=True)
    return {
        "roster": len(athletes),
        "out": [a.get("shortName") or a.get("displayName") for a in out],
        "outPay": sum(salary(a, season_year) for a in out),  # combined yearly salary of players out
    }


def previous_data(path):
    """The DATA object embedded in a previously built page, or None."""
    if not path:
        return None
    try:
        html = Path(path).read_text()
        m = re.search(r"const DATA = (\{.*?\});\s*\n", html, re.S)
        return json.loads(m.group(1)) if m else None
    except (OSError, ValueError):
        return None


def game_from_event(day_key, ev):
    comp = ev["competitions"][0]
    side = {c["homeAway"]: c for c in comp["competitors"]}
    national = [
        g["media"]["shortName"]
        for g in comp.get("geoBroadcasts", [])
        if g.get("market", {}).get("type") == "National"
    ]
    service, channel = "leaguepass", None
    for name in national:
        s = SERVICE_OF.get(name.lower())
        if s:
            service, channel = s, name
            break
    if service == "leaguepass" and national:
        channel = national[0]  # e.g. NBA TV
    notes = " ".join(n.get("headline", "") for n in comp.get("notes", []))
    status = ev.get("status", {}).get("type", {})

    def team(c):
        t = c["team"]
        rec = next((r.get("summary") for r in c.get("records") or [] if r.get("type") == "total"), None)
        return {
            "id": t["id"],
            "name": t["name"],
            "abbr": t.get("abbreviation", ""),
            "color": t.get("color") or "333333",
            "alt": t.get("alternateColor") or "777777",
            "rec": rec,
            "score": c.get("score"),
        }

    link = next((l.get("href") for l in ev.get("links", []) if (l.get("href") or "").startswith("https://www.espn.com/")), None)
    a, h = team(side["away"]), team(side["home"])
    return {
        "id": ev.get("id"),
        "day": day_key,
        "start": ev["date"],
        "awayId": a["id"],
        "homeId": h["id"],
        "away": a["name"],
        "home": h["name"],
        "a": a,
        "h": h,
        "state": status.get("state", "pre"),   # pre / in / post at build time
        "detail": status.get("shortDetail"),
        "period": ev.get("status", {}).get("period"),
        "clock": ev.get("status", {}).get("displayClock"),
        "link": link,
        "service": service,
        "channel": channel,
        "cup": "NBA Cup" in notes,
    }


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--prev", help="saved HTML of the live page, to reuse its injury lists")
    opts = args.parse_args()
    now = datetime.now(ET)
    today = now.date()
    games = []
    for i in range(DAYS):
        day = today + timedelta(days=i)
        for ev in fetch_day(day).get("events", []):
            games.append(game_from_event(day.isoformat(), ev))
    games.sort(key=lambda g: g["start"])
    team_ids = sorted({g["awayId"] for g in games} | {g["homeId"] for g in games})

    # Injuries: refresh at the first build after today's 6:30 PM; otherwise keep the live page's lists.
    cutoff = now.replace(hour=INJURY_REFRESH[0], minute=INJURY_REFRESH[1], second=0, microsecond=0)
    prev = previous_data(opts.prev) or {}
    prev_teams = prev.get("teams") or {}
    prev_at = prev.get("injuriesAt")
    prev_at = datetime.fromisoformat(prev_at) if prev_at else None
    stale = (not prev_teams or prev_at is None or "outPay" not in next(iter(prev_teams.values()), {})
             or (now >= cutoff and prev_at < cutoff))
    if stale:
        teams = {tid: team_status(tid) for tid in team_ids}
        injuries_at = now
    else:
        teams = {tid: prev_teams[tid] if tid in prev_teams else team_status(tid) for tid in team_ids}
        injuries_at = prev_at
    data = {
        "updated": now.isoformat(timespec="minutes"),
        "injuriesAt": injuries_at.isoformat(timespec="minutes"),
        "games": games,
        "teams": teams,
    }
    html = (HERE / "template.html").read_text()
    html = html.replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (HERE / "index.html").write_text(html)
    print(f"Wrote index.html: {len(games)} games from {today} for {DAYS} days; "
          f"injuries {'refreshed' if stale else 'kept from ' + injuries_at.strftime('%b %d %I:%M %p')}")


if __name__ == "__main__":
    main()
