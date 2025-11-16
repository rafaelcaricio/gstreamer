"""
Buffer: Data container for mini-GStreamer

Simplified version of GstBuffer that holds:
- Data payload (simulated media content)
- Presentation timestamp (pts)
- Duration
- Flags (DISCONT, EOS, etc.)
- Sequence number for tracking
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import IntFlag
import time


class BufferFlags(IntFlag):
    """Buffer flags similar to GstBufferFlags"""
    NONE = 0
    DISCONT = 1 << 0      # Discontinuity in the stream
    DELTA_UNIT = 1 << 1   # Not a keyframe
    EOS = 1 << 2          # End of stream marker
    CORRUPTED = 1 << 3    # Data might be corrupted


@dataclass
class Buffer:
    """
    Simple buffer to carry data through the pipeline.

    In real GStreamer, this would be GstBuffer with memory management,
    metadata, and more. Here we keep it simple.
    """
    data: Any  # The actual payload (could be bytes, string, dict, etc.)
    pts: float = 0.0  # Presentation timestamp in seconds
    duration: float = 0.0  # Duration in seconds
    sequence: int = 0  # Sequence number for tracking
    flags: BufferFlags = BufferFlags.NONE

    # Metadata (flexible dict for element-specific data)
    metadata: dict = field(default_factory=dict)

    # Reference counting (simplified - in real GStreamer this is in GstMiniObject)
    _refcount: int = field(default=1, init=False, repr=False)

    def ref(self) -> 'Buffer':
        """Increase reference count (simplified version of gst_buffer_ref)"""
        self._refcount += 1
        return self

    def unref(self) -> None:
        """Decrease reference count (simplified version of gst_buffer_unref)"""
        self._refcount -= 1
        if self._refcount <= 0:
            # In real implementation, this would free memory
            pass

    def is_writable(self) -> bool:
        """Check if buffer can be modified (refcount == 1)"""
        return self._refcount == 1

    def make_writable(self) -> 'Buffer':
        """
        Make buffer writable (simplified version of gst_buffer_make_writable).
        If refcount > 1, creates a copy.
        """
        if self.is_writable():
            return self

        # Create a copy
        import copy
        new_buffer = copy.deepcopy(self)
        new_buffer._refcount = 1
        self.unref()
        return new_buffer

    def has_flags(self, flags: BufferFlags) -> bool:
        """Check if buffer has specific flags set"""
        return bool(self.flags & flags)

    def set_flags(self, flags: BufferFlags) -> None:
        """Set additional flags on buffer"""
        self.flags |= flags

    def __repr__(self) -> str:
        flags_str = str(self.flags).replace('BufferFlags.', '')
        data_preview = str(self.data)[:50] + "..." if len(str(self.data)) > 50 else str(self.data)
        return (f"Buffer(seq={self.sequence}, pts={self.pts:.3f}s, "
                f"dur={self.duration:.3f}s, flags={flags_str}, "
                f"data='{data_preview}')")


class BufferList:
    """
    Container for multiple buffers (simplified GstBufferList).
    Some elements work more efficiently with buffer lists.
    """
    def __init__(self):
        self.buffers: list[Buffer] = []

    def add(self, buffer: Buffer) -> None:
        """Add buffer to the list"""
        self.buffers.append(buffer)

    def get(self, index: int) -> Optional[Buffer]:
        """Get buffer at index"""
        if 0 <= index < len(self.buffers):
            return self.buffers[index]
        return None

    def length(self) -> int:
        """Get number of buffers in list"""
        return len(self.buffers)

    def __iter__(self):
        return iter(self.buffers)

    def __len__(self):
        return len(self.buffers)
