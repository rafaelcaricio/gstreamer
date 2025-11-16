"""GstClock - Timing and synchronization."""

import time
from typing import Tuple


class GstClockReturn:
    """Return values from clock operations."""
    OK = "ok"
    EARLY = "early"
    UNSCHEDULED = "unscheduled"
    BADTIME = "badtime"


class GstClock:
    """
    Simplified GstClock for timing and synchronization.

    Corresponds to gst_clock_id_wait in gstbasesink.c:2381
    """

    def __init__(self):
        """Create a clock."""
        self._start_time = None

    def start(self):
        """Start the clock (called when pipeline goes to PLAYING)."""
        self._start_time = time.monotonic()

    def get_time(self) -> float:
        """
        Get current clock time in seconds.

        Returns:
            Time in seconds since clock started, or 0 if not started
        """
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    def wait_until(self, target_time: float) -> Tuple[str, float]:
        """
        Wait until the clock reaches the target time.

        This is similar to gst_clock_id_wait in gstbasesink.c:2381

        Args:
            target_time: Target time to wait for (in seconds)

        Returns:
            Tuple of (GstClockReturn, jitter in seconds)
            - jitter > 0: woke up late
            - jitter < 0: woke up early
            - jitter = 0: perfect timing
        """
        if self._start_time is None:
            return (GstClockReturn.BADTIME, 0.0)

        current = self.get_time()
        wait_duration = target_time - current

        if wait_duration <= 0:
            # Already past target time - return immediately with negative jitter
            jitter = -wait_duration
            return (GstClockReturn.OK, jitter)

        # Sleep until target time
        time.sleep(wait_duration)

        # Calculate jitter (how far off we were)
        actual_time = self.get_time()
        jitter = actual_time - target_time

        return (GstClockReturn.OK, jitter)

    def __repr__(self) -> str:
        if self._start_time is None:
            return "GstClock(stopped)"
        return f"GstClock(time={self.get_time():.3f}s)"
