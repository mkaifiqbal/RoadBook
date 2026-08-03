"""
FMCSA Hours-of-Service simulation engine (49 CFR Part 395).

Pure Python, no Django imports -- so it can be unit tested in isolation and
reasoned about on its own.  The engine takes a route (already resolved to
distance + drive time per leg) plus the driver's current 70hr/8-day usage and
produces a minute-accurate duty-status timeline, which is then sliced into
midnight-to-midnight daily log sheets.

Rules implemented
-----------------
11-hour driving limit      395.3(a)(3)  -- max 11 hrs driving per duty window
14-hour driving window     395.3(a)(2)  -- clock starts when the driver comes
                                           on duty and never pauses
30-minute break            395.3(a)(3)(ii) -- required after 8 cumulative hours
                                           of driving; satisfied by any 30
                                           consecutive minutes NOT driving
                                           (off duty OR on duty not driving)
10 consecutive hours off   395.3(a)(1)  -- required before a new window
70 hours / 8 days          395.3(b)(2)  -- rolling cycle for a carrier
                                           operating every day of the week
34-hour restart            395.3(c)     -- resets the cycle

Operating assumptions (from the brief, not from the regulation)
---------------------------------------------------------------
* Property-carrying driver, 70hr/8-day cycle.
* No adverse driving conditions exception (395.1(b)).
* No sleeper-berth split provision; the standalone 30-minute break is logged
  in the sleeper berth, while 10/34-hour resets remain Off Duty.
* Fueling at least once every 1,000 miles, 30 min on duty (not driving).
* 1 hour on duty (not driving) at pickup and 1 hour at drop-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------------
# Duty statuses -- these map 1:1 onto the four rows of the paper log grid.
# --------------------------------------------------------------------------
OFF_DUTY = "off_duty"
SLEEPER = "sleeper_berth"
DRIVING = "driving"
ON_DUTY = "on_duty"

STATUS_ROWS = [OFF_DUTY, SLEEPER, DRIVING, ON_DUTY]
STATUS_LABELS = {
    OFF_DUTY: "Off Duty",
    SLEEPER: "Sleeper Berth",
    DRIVING: "Driving",
    ON_DUTY: "On Duty (not driving)",
}

# --------------------------------------------------------------------------
# Regulatory limits, in minutes.
# --------------------------------------------------------------------------
MAX_DRIVE_PER_WINDOW = 11 * 60
MAX_WINDOW = 14 * 60
DRIVE_BEFORE_BREAK = 8 * 60
BREAK_MINUTES = 30
REQUIRED_OFF_DUTY = 10 * 60
CYCLE_LIMIT = 70 * 60
CYCLE_DAYS = 8
RESTART_MINUTES = 34 * 60

# --------------------------------------------------------------------------
# Operating assumptions.
# --------------------------------------------------------------------------
FUEL_INTERVAL_MILES = 1000.0
FUEL_STOP_MINUTES = 30
PICKUP_MINUTES = 60
DROPOFF_MINUTES = 60

# Fallback average speed if a leg arrives without a duration.
DEFAULT_SPEED_MPH = 55.0

ASSUMPTIONS = [
    "Property-carrying driver on the 70 hour / 8 day cycle.",
    "No adverse driving conditions exception claimed (395.1(b)).",
    "No sleeper-berth split provision is used. A standalone 30-minute break "
    "is logged as Sleeper Berth; 10-hour rests and 34-hour restarts are Off Duty.",
    "Fuel stop every 1,000 miles, 30 minutes on duty (not driving).",
    "1 hour on duty (not driving) for pickup and 1 hour for drop-off.",
    "The 30-minute break is satisfied by any 30 consecutive non-driving "
    "minutes, so a fuel stop or the pickup/drop-off hour can satisfy it.",
    "Saved Roadbook trips use dated duty history for the rolling 8-day total. "
    "A manually declared starting total is assigned to the prior day.",
    "At 70 hours the driver may remain on duty but cannot drive until hours "
    "roll off or a qualifying 34-hour restart is completed.",
]


class HOSViolation(Exception):
    """Raised when a trip cannot be planned inside the regulation."""


# --------------------------------------------------------------------------
# Inputs / outputs
# --------------------------------------------------------------------------
@dataclass
class Leg:
    """One routed segment of the trip."""

    origin: str
    destination: str
    miles: float
    drive_minutes: float

    @property
    def speed_mph(self) -> float:
        if self.drive_minutes <= 0:
            return DEFAULT_SPEED_MPH
        return self.miles / (self.drive_minutes / 60.0)


@dataclass
class Event:
    """A single continuous block of one duty status."""

    status: str
    activity: str  # drive | pickup | dropoff | fuel | break | rest | restart
    start: datetime
    end: datetime
    miles: float = 0.0
    miles_from_origin: float = 0.0  # cumulative trip miles at `start`
    label: str = ""

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "status_label": STATUS_LABELS[self.status],
            "activity": self.activity,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "minutes": round(self.minutes, 1),
            "miles": round(self.miles, 1),
            "miles_from_origin": round(self.miles_from_origin, 1),
            "label": self.label,
        }


# --------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------
class HOSPlanner:
    """Walks the trip forward in duty-status blocks, obeying Part 395."""

    def __init__(
        self,
        legs: list[Leg],
        start_time: datetime,
        cycle_used_hours: float = 0.0,
        fuel_interval_miles: float = FUEL_INTERVAL_MILES,
        cycle_state: dict | None = None,
    ) -> None:
        if not legs:
            raise ValueError("at least one leg is required")
        if cycle_used_hours < 0 or cycle_used_hours > 70:
            raise ValueError("current cycle used must be between 0 and 70 hours")

        self.legs = legs
        self.start_time = start_time
        self.fuel_interval_miles = fuel_interval_miles

        self.events: list[Event] = []
        self.now = start_time

        # The state from a saved trip carries both rolling-cycle history and an
        # unfinished 11/14-hour duty window into the driver's next trip.
        self.window_start = start_time
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0
        self.duty_by_day: dict[date, float] = {}
        self.cycle_source = "declared"
        if cycle_state:
            self._restore_state(cycle_state)
            self.cycle_source = "driver_history"
        elif cycle_used_hours:
            # An aggregate entered without Roadbook history has no dated
            # breakdown. Attribute it to the prior day so it participates in
            # the rolling 8-day window instead of remaining forever.
            self.duty_by_day[start_time.date() - timedelta(days=1)] = cycle_used_hours * 60.0
        self.initial_cycle_used = self.cycle_used

        self.total_miles = 0.0
        self.miles_since_fuel = 0.0
        self.restarts = 0

        # Guard against a pathological input producing an unbounded loop.
        self._guard = 0

    # -- cycle bookkeeping -------------------------------------------------
    @property
    def cycle_used(self) -> float:
        """On-duty minutes counting against the 70/8 rolling window."""
        cutoff = self.now.date() - timedelta(days=CYCLE_DAYS - 1)
        rolled = sum(m for d, m in self.duty_by_day.items() if d >= cutoff)
        return rolled

    def _restore_state(self, state: dict) -> None:
        previous_end = datetime.fromisoformat(state["end_time"])
        if self.start_time < previous_end:
            raise ValueError("Trip start must be after the driver's previous trip ends.")

        self.duty_by_day = {
            date.fromisoformat(day): float(minutes)
            for day, minutes in state.get("duty_by_day", {}).items()
        }
        gap = (self.start_time - previous_end).total_seconds() / 60.0
        if gap >= RESTART_MINUTES:
            self.duty_by_day.clear()

        previous_window = state.get("window_start")
        self.window_start = datetime.fromisoformat(previous_window) if previous_window else self.start_time
        self.drive_in_window = float(state.get("drive_in_window", 0.0))
        self.drive_since_break = float(state.get("drive_since_break", 0.0))

        if gap >= REQUIRED_OFF_DUTY:
            self.window_start = self.start_time
            self.drive_in_window = 0.0
            self.drive_since_break = 0.0
        elif gap >= BREAK_MINUTES:
            self.drive_since_break = 0.0

    def _accrue_duty(self, start: datetime, end: datetime) -> None:
        """Add on-duty minutes to the calendar days they actually fall on."""
        cursor = start
        while cursor < end:
            midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
            chunk_end = min(end, midnight)
            minutes = (chunk_end - cursor).total_seconds() / 60.0
            self.duty_by_day[cursor.date()] = self.duty_by_day.get(cursor.date(), 0.0) + minutes
            cursor = chunk_end

    # -- primitive -------------------------------------------------------
    def _add(
        self,
        status: str,
        activity: str,
        minutes: float,
        miles: float = 0.0,
        label: str = "",
    ) -> Event:
        if minutes <= 0:
            raise ValueError(f"{activity}: non-positive duration {minutes}")

        event = Event(
            status=status,
            activity=activity,
            start=self.now,
            end=self.now + timedelta(minutes=minutes),
            miles=miles,
            miles_from_origin=self.total_miles,
            label=label,
        )
        self.events.append(event)
        self.now = event.end

        if status == DRIVING:
            self.drive_in_window += minutes
            self.drive_since_break += minutes
            self.total_miles += miles
            self.miles_since_fuel += miles
            self._accrue_duty(event.start, event.end)
        elif status == ON_DUTY:
            self._accrue_duty(event.start, event.end)

        # 395.3(a)(3)(ii): any 30 consecutive minutes not driving -- off duty
        # OR on duty not driving -- satisfies the break requirement.
        if status != DRIVING and minutes >= BREAK_MINUTES:
            self.drive_since_break = 0.0

        return event

    @property
    def window_elapsed(self) -> float:
        return (self.now - self.window_start).total_seconds() / 60.0

    # -- inserted rest events ---------------------------------------------
    def _take_break(self) -> None:
        self._add(
            SLEEPER,
            "break",
            BREAK_MINUTES,
            label="30-minute sleeper break (8 hrs driving reached)",
        )

    def _take_rest(self) -> None:
        self._add(OFF_DUTY, "rest", REQUIRED_OFF_DUTY, label="10-hour off-duty reset")
        # A new 14-hour window opens when the driver next comes on duty.
        self.window_start = self.now
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0

    def _take_restart(self) -> None:
        self._add(OFF_DUTY, "restart", RESTART_MINUTES, label="34-hour restart (70-hour cycle exhausted)")
        self.duty_by_day.clear()
        self.window_start = self.now
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0
        self.restarts += 1

    def _recover_cycle(self) -> None:
        """Wait for dated hours to roll off when that is faster than a restart."""
        cutoff = self.now.date() - timedelta(days=CYCLE_DAYS - 1)
        active_days = sorted(day for day, minutes in self.duty_by_day.items() if day >= cutoff and minutes > 0)
        if not active_days:
            self._take_restart()
            return

        rollover = datetime.combine(active_days[0] + timedelta(days=CYCLE_DAYS), datetime.min.time())
        wait_minutes = max((rollover - self.now).total_seconds() / 60.0, 0.0)
        if wait_minutes <= 0.01 or wait_minutes >= RESTART_MINUTES:
            self._take_restart()
            return

        self._add(
            OFF_DUTY,
            "cycle_wait",
            wait_minutes,
            label=f"Off duty until {active_days[0].isoformat()} hours roll off",
        )
        if wait_minutes >= REQUIRED_OFF_DUTY:
            self.window_start = self.now
            self.drive_in_window = 0.0
            self.drive_since_break = 0.0

    def _fuel_stop(self) -> None:
        self._add(
            ON_DUTY,
            "fuel",
            FUEL_STOP_MINUTES,
            label=f"Fuel stop ({self.total_miles:,.0f} mi)",
        )
        self.miles_since_fuel = 0.0

    # -- the gate before every driving chunk ------------------------------
    def _clear_to_drive(self) -> None:
        """Insert whatever rest/break/fuel is required before driving again."""
        while True:
            self._guard += 1
            if self._guard > 10_000:
                raise HOSViolation("HOS simulation failed to converge")

            if self.cycle_used >= CYCLE_LIMIT:
                self._recover_cycle()
                continue
            if self.drive_in_window >= MAX_DRIVE_PER_WINDOW or self.window_elapsed >= MAX_WINDOW:
                self._take_rest()
                continue
            if self.drive_since_break >= DRIVE_BEFORE_BREAK:
                self._take_break()
                continue
            if self.miles_since_fuel >= self.fuel_interval_miles:
                self._fuel_stop()
                continue
            return

    # -- driving -----------------------------------------------------------
    def _drive_leg(self, leg: Leg) -> None:
        remaining = leg.drive_minutes
        speed = leg.speed_mph
        label = f"En route to {leg.destination}"

        while remaining > 0.01:
            self._clear_to_drive()

            miles_to_fuel = max(self.fuel_interval_miles - self.miles_since_fuel, 0.0)
            chunk = min(
                remaining,
                MAX_DRIVE_PER_WINDOW - self.drive_in_window,
                MAX_WINDOW - self.window_elapsed,
                DRIVE_BEFORE_BREAK - self.drive_since_break,
                CYCLE_LIMIT - self.cycle_used,
                miles_to_fuel / speed * 60.0,
            )
            if chunk <= 0.01:
                # A limit binds exactly here; let the gate insert the fix.
                continue

            self._add(DRIVING, "drive", chunk, miles=speed * chunk / 60.0, label=label)
            remaining -= chunk

    # -- on-duty work ------------------------------------------------------
    def _work(self, activity: str, minutes: float, label: str) -> None:
        # Work that is not driving may legally continue past the 14-hour
        # window and past the cycle limit. Section 395.3(b) prohibits driving
        # after 70 hours; it does not prohibit on-duty-not-driving work.
        self._add(ON_DUTY, activity, minutes, label=label)

    # -- entry point -------------------------------------------------------
    def run(self) -> list[Event]:
        pickup = self.legs[0].destination
        dropoff = self.legs[-1].destination

        self._drive_leg(self.legs[0])
        self._work("pickup", PICKUP_MINUTES, f"Pickup at {pickup} (1 hr loading)")

        for leg in self.legs[1:]:
            self._drive_leg(leg)

        self._work("dropoff", DROPOFF_MINUTES, f"Drop-off at {dropoff} (1 hr unloading)")
        return self.events


# --------------------------------------------------------------------------
# Daily log sheets
# --------------------------------------------------------------------------
def _minutes_into_day(moment: datetime, day: date) -> float:
    return (moment - datetime.combine(day, datetime.min.time())).total_seconds() / 60.0


def split_into_daily_logs(events: list[Event]) -> list[dict]:
    """Slice the timeline at midnight into one log sheet per calendar day.

    Each sheet is midnight-to-midnight and always covers the full 1440
    minutes -- any uncovered head/tail of a day is filled with Off Duty, the
    way a real log sheet has to be.
    """
    if not events:
        return []

    # 1. Cut every event at midnight boundaries.
    pieces: list[tuple[date, float, float, Event]] = []
    for event in events:
        cursor = event.start
        while cursor < event.end:
            day = cursor.date()
            midnight = datetime.combine(day + timedelta(days=1), datetime.min.time())
            piece_end = min(event.end, midnight)
            pieces.append(
                (
                    day,
                    _minutes_into_day(cursor, day),
                    _minutes_into_day(piece_end, day),
                    event,
                )
            )
            cursor = piece_end

    # 2. Group by day, pad with Off Duty, and total each status.
    first_day = events[0].start.date()
    last_day = (events[-1].end - timedelta(microseconds=1)).date()

    logs = []
    day = first_day
    day_number = 1
    while day <= last_day:
        day_pieces = [p for p in pieces if p[0] == day]
        day_pieces.sort(key=lambda p: p[1])

        entries: list[dict] = []
        remarks: list[dict] = []
        cursor = 0.0

        for _, start_min, end_min, event in day_pieces:
            if start_min > cursor + 0.01:
                entries.append(
                    {
                        "status": OFF_DUTY,
                        "activity": "off_duty",
                        "start_minute": round(cursor, 1),
                        "end_minute": round(start_min, 1),
                        "label": "Off duty",
                    }
                )
            entries.append(
                {
                    "status": event.status,
                    "activity": event.activity,
                    "start_minute": round(start_min, 1),
                    "end_minute": round(end_min, 1),
                    "label": event.label,
                }
            )
            # A remark is only written where the status actually changes, i.e.
            # where the event genuinely begins (not at a midnight carry-over).
            if abs(_minutes_into_day(event.start, day) - start_min) < 0.01:
                remarks.append(
                    {
                        "minute": round(start_min, 1),
                        "time": _fmt_clock(start_min),
                        "status": event.status,
                        "activity": event.activity,
                        "label": event.label or STATUS_LABELS[event.status],
                    }
                )
            cursor = end_min

        if cursor < 1440.0 - 0.01:
            entries.append(
                {
                    "status": OFF_DUTY,
                    "activity": "off_duty",
                    "start_minute": round(cursor, 1),
                    "end_minute": 1440.0,
                    "label": "Off duty",
                }
            )

        # Merge adjacent entries that share a status so the drawn grid is a
        # clean step line instead of a stack of invisible seams.
        merged: list[dict] = []
        for entry in entries:
            if merged and merged[-1]["status"] == entry["status"] and abs(merged[-1]["end_minute"] - entry["start_minute"]) < 0.01:
                merged[-1]["end_minute"] = entry["end_minute"]
            else:
                merged.append(dict(entry))

        totals = {status: 0.0 for status in STATUS_ROWS}
        for entry in merged:
            totals[entry["status"]] += entry["end_minute"] - entry["start_minute"]

        miles = sum(
            event.miles * ((end_min - start_min) / event.minutes)
            for _, start_min, end_min, event in day_pieces
            if event.status == DRIVING and event.minutes > 0
        )

        logs.append(
            {
                "day_number": day_number,
                "date": day.isoformat(),
                "entries": merged,
                "remarks": remarks,
                "totals_minutes": {k: round(v, 1) for k, v in totals.items()},
                "totals_hours": {k: round(v / 60.0, 2) for k, v in totals.items()},
                "total_on_duty_hours": round((totals[DRIVING] + totals[ON_DUTY]) / 60.0, 2),
                "miles_driving_today": round(miles),
            }
        )
        day += timedelta(days=1)
        day_number += 1

    return logs


def _fmt_clock(minute: float) -> str:
    minute = int(round(minute))
    return f"{minute // 60 % 24:02d}:{minute % 60:02d}"


# --------------------------------------------------------------------------
# Public helper: run the sim and package everything up.
# --------------------------------------------------------------------------
STOP_ACTIVITIES = {"pickup", "dropoff", "fuel", "break", "rest", "restart", "cycle_wait"}


def plan_trip(
    legs: list[Leg],
    start_time: datetime,
    cycle_used_hours: float = 0.0,
    fuel_interval_miles: float = FUEL_INTERVAL_MILES,
    cycle_state: dict | None = None,
) -> dict:
    planner = HOSPlanner(legs, start_time, cycle_used_hours, fuel_interval_miles, cycle_state)
    events = planner.run()
    logs = split_into_daily_logs(events)

    driving = sum(e.minutes for e in events if e.status == DRIVING)
    on_duty = sum(e.minutes for e in events if e.status == ON_DUTY)
    off_duty = sum(e.minutes for e in events if e.status == OFF_DUTY)

    stops = [
        {
            "type": e.activity,
            "label": e.label,
            "arrive": e.start.isoformat(),
            "depart": e.end.isoformat(),
            "minutes": round(e.minutes),
            "miles_from_origin": round(e.miles_from_origin, 1),
        }
        for e in events
        if e.activity in STOP_ACTIVITIES
    ]

    return {
        "events": [e.to_dict() for e in events],
        "stops": stops,
        "logs": logs,
        "summary": {
            "start_time": start_time.isoformat(),
            "end_time": events[-1].end.isoformat(),
            "total_miles": round(planner.total_miles),
            "days": len(logs),
            "driving_hours": round(driving / 60.0, 2),
            "on_duty_not_driving_hours": round(on_duty / 60.0, 2),
            "off_duty_hours": round(off_duty / 60.0, 2),
            "cycle_used_at_start": round(planner.initial_cycle_used / 60.0, 2),
            "cycle_used_at_end": round(planner.cycle_used / 60.0, 2),
            "cycle_remaining": round(max(CYCLE_LIMIT - planner.cycle_used, 0.0) / 60.0, 2),
            "cycle_source": planner.cycle_source,
            "restarts_required": planner.restarts,
            "ten_hour_resets": sum(1 for e in events if e.activity == "rest"),
            "thirty_minute_breaks": sum(1 for e in events if e.activity == "break"),
            "fuel_stops": sum(1 for e in events if e.activity == "fuel"),
            "cycle_state": {
                "end_time": events[-1].end.isoformat(),
                "window_start": planner.window_start.isoformat(),
                "drive_in_window": round(planner.drive_in_window, 2),
                "drive_since_break": round(planner.drive_since_break, 2),
                "duty_by_day": {
                    day.isoformat(): round(minutes, 2)
                    for day, minutes in sorted(planner.duty_by_day.items())
                },
            },
        },
        "assumptions": ASSUMPTIONS,
    }
