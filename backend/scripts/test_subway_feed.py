"""
Isolated test: fetch live subway arrival predictions for the 6 @ 77 St
and the Q @ 72 St / 86 St (downtown direction, i.e. towards work).

Not imported by the app -- run directly to sanity-check the feed:

    py -3 backend/scripts/test_subway_feed.py

Stop IDs come from MTA's official Stations.csv
(http://web.mta.info/developers/data/nyct/subway/Stations.csv):
  6 @ 77 St  -> base stop_id 627 (downtown = 627S)
  Q @ 72 St  -> base stop_id Q03 (downtown = Q03S)
  Q @ 86 St  -> base stop_id Q04 (downtown = Q04S)
"""

from datetime import datetime

from nyct_gtfs import NYCTFeed

TARGETS = [
    ("6", "627S", "6 train @ 77 St (downtown)"),
    ("Q", "Q03S", "Q train @ 72 St (downtown)"),
    ("Q", "Q04S", "Q train @ 86 St (downtown)"),
]


def minutes_until(arrival: datetime) -> float:
    now = datetime.now(arrival.tzinfo) if arrival.tzinfo else datetime.now()
    return (arrival - now).total_seconds() / 60


def print_arrivals(line: str, stop_id: str, label: str) -> None:
    feed = NYCTFeed(line)
    trips = feed.filter_trips(headed_for_stop_id=[stop_id], underway=True)

    print(f"\n{label} -- {len(trips)} upcoming trip(s)")
    for trip in trips:
        for stu in trip.stop_time_updates:
            if stu.stop_id == stop_id:
                print(
                    f"  {trip.route_id} to {trip.headsign_text}: "
                    f"arrives in {minutes_until(stu.arrival):.1f} min "
                    f"(raw: {stu.arrival})"
                )


if __name__ == "__main__":
    for line, stop_id, label in TARGETS:
        print_arrivals(line, stop_id, label)
