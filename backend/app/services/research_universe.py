from __future__ import annotations


# Autonomous Research Lab universe.
#
# Keep this separate from the intraday scanner universe: increasing the depth of
# unattended research must not silently increase the latency or blast radius of
# the public real-time scanner endpoint. The first 20 symbols preserve the
# production research universe that already accumulated TRAIN_ONLY memory. The
# second 20 are long-lived, liquid TWSE names used to broaden sector coverage.
CORE_RESEARCH_UNIVERSE = (
    "0050",
    "0056",
    "00878",
    "00919",
    "2330",
    "2317",
    "2454",
    "2308",
    "2382",
    "2303",
    "2345",
    "2379",
    "2881",
    "2882",
    "2891",
    "2603",
    "2615",
    "3037",
    "3231",
    "3711",
)

RESEARCH_EXPANSION_UNIVERSE = (
    "1101",
    "1216",
    "1301",
    "1303",
    "2002",
    "2207",
    "2327",
    "2357",
    "2376",
    "2395",
    "2412",
    "2884",
    "2885",
    "2886",
    "2892",
    "3008",
    "3045",
    "4904",
    "5880",
    "6505",
)

DAILY_RESEARCH_UNIVERSE = CORE_RESEARCH_UNIVERSE + RESEARCH_EXPANSION_UNIVERSE

if len(DAILY_RESEARCH_UNIVERSE) != 40:
    raise RuntimeError("Daily autonomous research universe must contain 40 symbols")
if len(set(DAILY_RESEARCH_UNIVERSE)) != len(DAILY_RESEARCH_UNIVERSE):
    raise RuntimeError("Daily autonomous research universe contains duplicates")
