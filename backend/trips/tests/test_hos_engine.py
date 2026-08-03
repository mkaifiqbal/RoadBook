"""Unit tests for the HOS engine.

The interesting one is `assert_compliant`: an independent re-implementation of
the Part 395 limits that walks the produced timeline and fails if any rule is
broken. Every scenario below is run through it, so the engine is checked
against a second reading of the regulation rather than against itself.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from trips.hos_engine import (
    DRIVING,
    OFF_DUTY,
    ON_DUTY,
    SLEEPER,
    Event,
    HOSPlanner,
    Leg,
    plan_trip,
    split_into_daily_logs,
)

EPS = 0.02  # minutes of float slack
START = datetime(2026, 3, 2, 6, 0)


def leg(origin: str, destination: str, miles: float, hours: float) -> Leg:
    return Leg(origin=origin, destination=destination, miles=miles, drive_minutes=hours * 60)


def assert_compliant(test: unittest.TestCase, events: list[Event], cycle_start_hours: float = 0.0):
    """Independently verify 11h / 14h / 30-min / 10h / 70h against a timeline."""
    window_start = None
    drive_in_window = 0.0
    drive_since_break = 0.0
    cycle = cycle_start_hours * 60.0

    for index, event in enumerate(events):
        minutes = event.minutes
        test.assertGreater(minutes, 0, f"event {index} has non-positive duration")
        if index:
            test.assertEqual(
                events[index - 1].end, event.start, f"gap/overlap before event {index}"
            )

        if event.status in (DRIVING, ON_DUTY):
            if window_start is None:
                window_start = event.start
            cycle += minutes
            test.assertLessEqual(cycle, 70 * 60 + EPS, f"70-hour cycle exceeded at event {index}")

        if event.status == DRIVING:
            elapsed = (event.end - window_start).total_seconds() / 60.0
            test.assertLessEqual(
                elapsed, 14 * 60 + EPS, f"drove past the 14-hour window at event {index}"
            )
            drive_in_window += minutes
            test.assertLessEqual(
                drive_in_window, 11 * 60 + EPS, f"11-hour driving limit exceeded at event {index}"
            )
            drive_since_break += minutes
            test.assertLessEqual(
                drive_since_break,
                8 * 60 + EPS,
                f"drove more than 8 hours without a 30-minute break at event {index}",
            )
        else:
            if minutes >= 30:
                drive_since_break = 0.0
            if event.status == OFF_DUTY and minutes >= 10 * 60:
                window_start = None
                drive_in_window = 0.0
                if minutes >= 34 * 60:
                    cycle = 0.0


class ShortTripTests(unittest.TestCase):
    def test_single_day_trip_needs_no_rest(self):
        legs = [leg("Chicago", "Joliet", 40, 0.75), leg("Joliet", "Peoria", 130, 2.25)]
        result = plan_trip(legs, START, cycle_used_hours=10)
        planner_events = _rebuild(legs, START, 10)

        assert_compliant(self, planner_events, 10)
        self.assertEqual(result["summary"]["ten_hour_resets"], 0)
        self.assertEqual(result["summary"]["thirty_minute_breaks"], 0)
        self.assertEqual(result["summary"]["fuel_stops"], 0)
        self.assertEqual(len(result["logs"]), 1)

    def test_pickup_and_dropoff_are_one_hour_on_duty_each(self):
        legs = [leg("A", "B", 40, 0.75), leg("B", "C", 60, 1.0)]
        events = _rebuild(legs, START, 0)
        pickup = [e for e in events if e.activity == "pickup"]
        dropoff = [e for e in events if e.activity == "dropoff"]

        self.assertEqual(len(pickup), 1)
        self.assertEqual(len(dropoff), 1)
        self.assertAlmostEqual(pickup[0].minutes, 60)
        self.assertAlmostEqual(dropoff[0].minutes, 60)
        self.assertEqual(pickup[0].status, ON_DUTY)
        self.assertEqual(dropoff[0].status, ON_DUTY)
        # Drop-off is the last thing that happens.
        self.assertIs(events[-1], dropoff[0])


class BreakRuleTests(unittest.TestCase):
    def test_thirty_minute_break_inserted_after_eight_hours_driving(self):
        legs = [leg("A", "B", 30, 0.5), leg("B", "C", 550, 10.0)]
        events = _rebuild(legs, START, 0)
        assert_compliant(self, events)

        breaks = [e for e in events if e.activity == "break"]
        self.assertEqual(len(breaks), 1)
        self.assertAlmostEqual(breaks[0].minutes, 30)
        self.assertEqual(breaks[0].status, SLEEPER)
        self.assertIn("sleeper break", breaks[0].label.lower())

        # The break must land exactly 8 driving-hours after the last thing
        # that reset the counter -- here, the 1-hour pickup.
        pickup_index = next(i for i, e in enumerate(events) if e.activity == "pickup")
        driving_since_reset = sum(
            e.minutes
            for e in events[pickup_index : events.index(breaks[0])]
            if e.status == DRIVING
        )
        self.assertAlmostEqual(driving_since_reset, 8 * 60, delta=EPS)

    def test_fuel_stop_satisfies_the_break_requirement(self):
        # 30-minute fuel stops land before 8 hours of driving accumulate, so
        # no separate off-duty break should ever be needed.
        legs = [leg("A", "B", 10, 0.2), leg("B", "C", 1400, 22.0)]
        events = _rebuild(legs, START, 0, fuel_interval_miles=350)
        assert_compliant(self, events)

        self.assertGreaterEqual(len([e for e in events if e.activity == "fuel"]), 3)
        self.assertEqual([e for e in events if e.activity == "break"], [])


class DrivingLimitTests(unittest.TestCase):
    def test_eleven_hour_limit_forces_a_ten_hour_reset(self):
        legs = [leg("A", "B", 20, 0.4), leg("B", "C", 900, 16.0)]
        events = _rebuild(legs, START, 0)
        assert_compliant(self, events)

        rests = [e for e in events if e.activity == "rest"]
        self.assertEqual(len(rests), 1)
        self.assertAlmostEqual(rests[0].minutes, 10 * 60)

        first_window_driving = sum(
            e.minutes for e in events[: events.index(rests[0])] if e.status == DRIVING
        )
        self.assertAlmostEqual(first_window_driving, 11 * 60, delta=EPS)

    def test_fourteen_hour_window_can_bind_before_the_eleven_hour_limit(self):
        # Frequent fuel stops burn the 14-hour clock without adding driving
        # time, so the window expires with driving hours still available.
        legs = [leg("A", "B", 10, 0.2), leg("B", "C", 1200, 20.0)]
        events = _rebuild(legs, START, 0, fuel_interval_miles=120)
        assert_compliant(self, events)

        rests = [e for e in events if e.activity == "rest"]
        self.assertGreaterEqual(len(rests), 1)

        first_rest = events.index(rests[0])
        driving = sum(e.minutes for e in events[:first_rest] if e.status == DRIVING)
        elapsed = (events[first_rest].start - events[0].start).total_seconds() / 60.0
        self.assertLess(driving, 11 * 60, "expected the 14-hour window to bind first")
        self.assertAlmostEqual(elapsed, 14 * 60, delta=EPS)

    def test_window_restarts_only_after_ten_consecutive_hours_off(self):
        legs = [leg("A", "B", 20, 0.4), leg("B", "C", 1400, 25.0)]
        events = _rebuild(legs, START, 0)
        assert_compliant(self, events)

        for rest in (e for e in events if e.activity == "rest"):
            self.assertEqual(rest.status, OFF_DUTY)
            self.assertAlmostEqual(rest.minutes, 10 * 60)


class FuelRuleTests(unittest.TestCase):
    def test_fuel_stop_at_least_every_thousand_miles(self):
        legs = [leg("A", "B", 50, 0.9), leg("B", "C", 2400, 40.0)]
        events = _rebuild(legs, START, 0)
        assert_compliant(self, events)

        miles_since_fuel = 0.0
        for event in events:
            if event.status == DRIVING:
                miles_since_fuel += event.miles
                self.assertLessEqual(miles_since_fuel, 1000 + 0.5)
            elif event.activity == "fuel":
                self.assertEqual(event.status, ON_DUTY)
                self.assertAlmostEqual(event.minutes, 30)
                miles_since_fuel = 0.0

        self.assertEqual(len([e for e in events if e.activity == "fuel"]), 2)


class CycleRuleTests(unittest.TestCase):
    def test_driver_near_the_seventy_hour_limit_must_take_a_34_hour_restart(self):
        legs = [leg("A", "B", 30, 0.5), leg("B", "C", 700, 12.0)]
        result = plan_trip(legs, START, cycle_used_hours=68)
        events = _rebuild(legs, START, 68)
        assert_compliant(self, events, 68)

        restarts = [e for e in events if e.activity == "restart"]
        self.assertEqual(len(restarts), 1)
        self.assertAlmostEqual(restarts[0].minutes, 34 * 60)
        self.assertEqual(result["summary"]["restarts_required"], 1)

        # Only two hours of the cycle were left, so that is all he may work
        # before the restart.
        on_duty_before = sum(
            e.minutes
            for e in events[: events.index(restarts[0])]
            if e.status in (DRIVING, ON_DUTY)
        )
        self.assertAlmostEqual(on_duty_before, 2 * 60, delta=EPS)

    def test_full_cycle_leaves_no_driving_before_a_restart(self):
        legs = [leg("A", "B", 30, 0.5), leg("B", "C", 200, 3.5)]
        events = _rebuild(legs, START, 70)
        assert_compliant(self, events, 70)
        self.assertEqual(events[0].activity, "restart")

    def test_rejects_impossible_cycle_input(self):
        legs = [leg("A", "B", 30, 0.5), leg("B", "C", 200, 3.5)]
        with self.assertRaises(ValueError):
            plan_trip(legs, START, cycle_used_hours=-1)
        with self.assertRaises(ValueError):
            plan_trip(legs, START, cycle_used_hours=71)

    def test_saved_cycle_state_is_used_on_the_next_trip(self):
        first = plan_trip(
            [leg("A", "B", 60, 1.0), leg("B", "C", 180, 3.0)],
            START,
            cycle_used_hours=10,
        )
        second_start = datetime.fromisoformat(first["summary"]["end_time"]) + timedelta(hours=10)
        second = plan_trip(
            [leg("C", "D", 60, 1.0), leg("D", "E", 180, 3.0)],
            second_start,
            cycle_used_hours=0,
            cycle_state=first["summary"]["cycle_state"],
        )

        self.assertEqual(second["summary"]["cycle_source"], "driver_history")
        self.assertAlmostEqual(
            second["summary"]["cycle_used_at_start"],
            first["summary"]["cycle_used_at_end"],
            delta=0.02,
        )

    def test_34_hours_between_saved_trips_resets_the_cycle(self):
        first = plan_trip(
            [leg("A", "B", 60, 1.0), leg("B", "C", 180, 3.0)], START, 25
        )
        second_start = datetime.fromisoformat(first["summary"]["end_time"]) + timedelta(hours=34)
        second = plan_trip(
            [leg("C", "D", 60, 1.0), leg("D", "E", 60, 1.0)],
            second_start,
            cycle_state=first["summary"]["cycle_state"],
        )

        self.assertEqual(second["summary"]["cycle_used_at_start"], 0)
        self.assertEqual(second["summary"]["restarts_required"], 0)

    def test_on_duty_dropoff_can_finish_after_cycle_reaches_seventy(self):
        result = plan_trip(
            [leg("A", "B", 30, 0.5), leg("B", "C", 30, 0.5)],
            START,
            cycle_used_hours=68,
        )

        self.assertEqual(result["events"][-1]["activity"], "dropoff")
        self.assertEqual(result["events"][-1]["status"], ON_DUTY)
        self.assertEqual(result["summary"]["restarts_required"], 0)
        self.assertGreater(result["summary"]["cycle_used_at_end"], 70)
        self.assertEqual(result["summary"]["cycle_remaining"], 0)


class DailyLogTests(unittest.TestCase):
    def setUp(self):
        self.legs = [leg("Chicago", "Denver", 1000, 16.0), leg("Denver", "Phoenix", 820, 13.0)]
        self.result = plan_trip(self.legs, START, cycle_used_hours=8)
        self.logs = self.result["logs"]

    def test_each_sheet_covers_a_full_24_hours(self):
        for log in self.logs:
            total = sum(log["totals_minutes"].values())
            self.assertAlmostEqual(total, 1440, delta=0.1, msg=f"{log['date']} is not 24 hours")

    def test_entries_are_contiguous_and_ordered(self):
        for log in self.logs:
            cursor = 0.0
            for entry in log["entries"]:
                self.assertAlmostEqual(entry["start_minute"], cursor, delta=0.05)
                self.assertGreater(entry["end_minute"], entry["start_minute"])
                cursor = entry["end_minute"]
            self.assertAlmostEqual(cursor, 1440, delta=0.05)

    def test_adjacent_entries_never_share_a_status(self):
        for log in self.logs:
            statuses = [entry["status"] for entry in log["entries"]]
            for a, b in zip(statuses, statuses[1:]):
                self.assertNotEqual(a, b, f"unmerged seam on {log['date']}")

    def test_dates_are_consecutive_and_multi_day(self):
        self.assertGreater(len(self.logs), 1)
        dates = [datetime.fromisoformat(log["date"]).date() for log in self.logs]
        for a, b in zip(dates, dates[1:]):
            self.assertEqual(b - a, timedelta(days=1))

    def test_daily_mileage_sums_to_the_trip_total(self):
        total = sum(log["miles_driving_today"] for log in self.logs)
        self.assertAlmostEqual(total, self.result["summary"]["total_miles"], delta=len(self.logs))

    def test_remarks_exist_for_every_status_change(self):
        remarked = sum(len(log["remarks"]) for log in self.logs)
        self.assertEqual(remarked, len(self.result["events"]))

    def test_totals_match_the_summary(self):
        driving = sum(log["totals_hours"]["driving"] for log in self.logs)
        self.assertAlmostEqual(driving, self.result["summary"]["driving_hours"], delta=0.05)

    def test_daily_on_duty_total_includes_driving_and_other_work(self):
        for log in self.logs:
            expected = log["totals_hours"]["driving"] + log["totals_hours"]["on_duty"]
            self.assertAlmostEqual(log["total_on_duty_hours"], expected, delta=0.02)


class TimelineIntegrityTests(unittest.TestCase):
    def test_timeline_is_gapless_across_many_scenarios(self):
        scenarios = [
            ([leg("A", "B", 5, 0.1), leg("B", "C", 20, 0.4)], 0.0),
            ([leg("A", "B", 300, 5.0), leg("B", "C", 300, 5.0)], 34.0),
            ([leg("A", "B", 60, 1.0), leg("B", "C", 3200, 55.0)], 12.0),
            ([leg("A", "B", 1100, 18.0), leg("B", "C", 1100, 18.0)], 65.0),
        ]
        for legs, cycle in scenarios:
            with self.subTest(cycle=cycle, miles=sum(l.miles for l in legs)):
                events = _rebuild(legs, START, cycle)
                assert_compliant(self, events, cycle)
                logs = split_into_daily_logs(events)
                for log in logs:
                    self.assertAlmostEqual(sum(log["totals_minutes"].values()), 1440, delta=0.1)

    def test_total_driving_time_equals_the_route_duration(self):
        legs = [leg("A", "B", 400, 7.0), leg("B", "C", 900, 15.0)]
        result = plan_trip(legs, START, 0)
        self.assertAlmostEqual(result["summary"]["driving_hours"], 22.0, delta=0.05)
        self.assertAlmostEqual(result["summary"]["total_miles"], 1300, delta=1)


def _rebuild(legs, start, cycle, fuel_interval_miles=1000.0) -> list[Event]:
    """Run the planner and hand back raw Event objects (not serialized)."""
    return HOSPlanner(legs, start, cycle, fuel_interval_miles).run()


if __name__ == "__main__":
    unittest.main()
