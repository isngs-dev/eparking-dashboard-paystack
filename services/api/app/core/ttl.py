"""TTL table per `.claude/skills/api-layer/SKILL.md`:

revenue/occupancy endpoints -> 5m soft / 15-30m hard.
/api/traffic/today          -> 2m soft / 10m hard (a "today" figure, needs to
                                feel current).
"""

from __future__ import annotations

STANDARD_SOFT_TTL = 5 * 60
STANDARD_HARD_TTL = 20 * 60  # midpoint of the skill's 15-30m hard-TTL range

TRAFFIC_TODAY_SOFT_TTL = 2 * 60
TRAFFIC_TODAY_HARD_TTL = 10 * 60

# Filters endpoint changes only when fee_categories is edited (rare, admin
# action) -- safe to cache longer than the revenue/occupancy default.
FILTERS_SOFT_TTL = 30 * 60
FILTERS_HARD_TTL = 60 * 60
