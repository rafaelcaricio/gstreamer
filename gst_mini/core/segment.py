"""GstSegment - Time domain conversion."""


class GstSegment:
    """
    Simplified GstSegment for stream time to running time conversion.

    Corresponds to gst_segment_to_running_time in gstsegment.c:822-867
    """

    def __init__(self, start: float = 0.0, stop: float = None, rate: float = 1.0, base: float = 0.0):
        """
        Create a segment.

        Args:
            start: Start time of the segment (in stream time)
            stop: Stop time of the segment (None = no limit)
            rate: Playback rate (1.0 = normal speed)
            base: Accumulated running time from previous segments
        """
        self.start = start
        self.stop = stop
        self.rate = rate
        self.base = base

    def to_running_time(self, position: float) -> float:
        """
        Convert stream time position to running time.

        Formula from gstsegment.c:822:
            running_time = (position - start) / rate + base

        Args:
            position: Position in stream time (e.g., buffer PTS)

        Returns:
            Running time, or -1 if position is outside segment boundaries
        """
        # Check if position is within segment boundaries
        if position < self.start:
            return -1.0

        if self.stop is not None and position > self.stop:
            return -1.0

        # Convert: (position - start) / rate + base
        running_time = (position - self.start) / self.rate + self.base

        return running_time

    def __repr__(self) -> str:
        stop_str = f"{self.stop:.3f}s" if self.stop is not None else "None"
        return f"GstSegment(start={self.start:.3f}s, stop={stop_str}, rate={self.rate}, base={self.base:.3f}s)"
