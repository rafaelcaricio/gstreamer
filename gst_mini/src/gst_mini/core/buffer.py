"""GstBuffer - Data container with timestamps."""

from enum import Flag, auto
from typing import Any, Dict


class BufferFlags(Flag):
    """Buffer flags similar to GstBufferFlags."""
    NONE = 0
    DISCONT = auto()  # Discontinuity in the stream
    EOS = auto()      # End of stream marker
    SEGMENT = auto()  # Segment marker (for HLS segments)
    DELTA_UNIT = auto()  # Indicates the buffer is not decodable by itself


class GstBuffer:
    """
    Simplified GstBuffer carrying timestamped data.

    Corresponds to GstBuffer in gstbuffer.h:80-133
    """

    def __init__(self, pts: float, duration: float, data: Any, flags: BufferFlags = BufferFlags.NONE):
        """
        Create a buffer.

        Args:
            pts: Presentation timestamp in seconds (like GST_BUFFER_PTS)
            duration: Buffer duration in seconds (like GST_BUFFER_DURATION)
            data: Payload data (dict for simulated frames, or segment info)
            flags: Buffer flags (DISCONT, EOS, etc.)
        """
        self.pts = pts
        self.duration = duration
        self.data = data
        self.flags = flags

    def has_flag(self, flag: BufferFlags) -> bool:
        """Check if buffer has a specific flag."""
        return bool(self.flags & flag)

    def set_flag(self, flag: BufferFlags):
        """Set a flag on the buffer."""
        self.flags |= flag

    def unset_flag(self, flag: BufferFlags):
        """Unset a flag on the buffer."""
        self.flags &= ~flag

    def __repr__(self) -> str:
        flags_str = ""
        if self.flags != BufferFlags.NONE:
            flags_str = f", flags={self.flags.name}"
        return f"GstBuffer(pts={self.pts:.3f}s, dur={self.duration:.3f}s{flags_str})"
