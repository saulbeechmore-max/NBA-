"""Build index.html for NBA Tonight.

Pulls the next 7 days of NBA games from ESPN's public scoreboard feed,
sorts each game onto the service that carries it (Prime Video, Peacock,
ESPN, or League Pass) and writes the data into template.html.

Usage: python3 build.py
"""
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
FEED = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={}"
ROSTER = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/roster"
DAYS = 7
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
    }


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
    return {
        "day": day_key,
        "start": ev["date"],
        "awayId": side["away"]["team"]["id"],
        "homeId": side["home"]["team"]["id"],
        "away": side["away"]["team"]["name"],
        "home": side["home"]["team"]["name"],
        "service": service,
        "channel": channel,
        "cup": "NBA Cup" in notes,
    }


def main():
    today = datetime.now(ET).date()
    games = []
    for i in range(DAYS):
        day = today + timedelta(days=i)
        for ev in fetch_day(day).get("events", []):
            games.append(game_from_event(day.isoformat(), ev))
    games.sort(key=lambda g: g["start"])
    team_ids = sorted({g["awayId"] for g in games} | {g["homeId"] for g in games})
    teams = {tid: team_status(tid) for tid in team_ids}
    data = {
        "updated": datetime.now(ET).isoformat(timespec="minutes"),
        "games": games,
        "teams": teams,
    }
    html = (HERE / "template.html").read_text()
    html = html.replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (HERE / "index.html").write_text(html)
    print(f"Wrote index.html: {len(games)} games from {today} for {DAYS} days")


if __name__ == "__main__":
    main()
