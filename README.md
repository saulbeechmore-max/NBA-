# NBA Tonight

A one-screen guide to which streaming service has tonight's NBA games:
Prime Video, Peacock, ESPN and League Pass. Tap a service to see its games;
tap a game to see how many players each team has available and who is out.

- `template.html`: the page design.
- `build.py`: pulls the next 7 days of games plus each team's roster and
  injury status from ESPN's public feed, and writes `index.html`.
- `index.html`: the built page (generated; don't edit by hand).

Rebuild: `python3 build.py` (Python 3.9+, no extra packages).

Published at https://claude.ai/artifact/1sj9e4ziJQQTviEduEbTYF and refreshed
twice a day by a scheduled Claude task.
