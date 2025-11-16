"""
HLSSegmenter: Splits stream into HLS-style segments

Like hlssink or splitmuxsink in GStreamer, this element:
- Accumulates buffers until segment duration is reached
- Creates complete "segment" buffers
- Pushes segments downstream for storage/upload

Demonstrates buffering and aggregation.
"""

import logging
from typing import List

from ..core import (
    Element, Buffer, BufferFlags, Pad, PadDirection, FlowReturn,
    State, StateChange, StateChangeReturn
)

logger = logging.getLogger(__name__)


class HLSSegmenter(Element):
    """
    Segments the stream into HLS-compatible chunks.

    Like hlssink, this:
    - Accumulates incoming buffers
    - When segment duration reached, emits a complete segment
    - Manages segment numbering and playlist
    """

    def __init__(self, name: str, segment_duration: float = 10.0):
        super().__init__(name)

        self.segment_duration = segment_duration  # Seconds per segment
        self.segment_number = 0

        # Current segment being built
        self.current_segment: List[Buffer] = []
        self.current_segment_start_time = 0.0
        self.current_segment_duration = 0.0

        # Create sink pad (input)
        self.sink_pad = Pad("sink", PadDirection.SINK, self)
        self.add_pad(self.sink_pad)

        # Create source pad (output)
        self.src_pad = Pad("src", PadDirection.SRC, self)
        self.add_pad(self.src_pad)

        # Register chain function
        self.sink_pad.set_chain_function(self._chain)

    def _chain(self, pad: Pad, buffer: Buffer) -> FlowReturn:
        """
        Chain function for the segmenter.

        Accumulates buffers and creates segments.
        """
        logger.info(f"    {self.name}.chain() - RECEIVED {buffer}")

        # Check for EOS
        if buffer.has_flags(BufferFlags.EOS):
            logger.info(f"    {self.name}.chain() - Got EOS")

            # Flush current segment if any
            if self.current_segment:
                logger.info(f"    {self.name}.chain() - Flushing final segment")
                ret = self._finish_segment()
                if ret != FlowReturn.OK:
                    return ret

            # Pass EOS downstream
            return self.src_pad.push(buffer)

        # Add buffer to current segment
        self._add_to_segment(buffer)

        # Check if segment is complete
        if self.current_segment_duration >= self.segment_duration:
            logger.info(f"    {self.name}.chain() - Segment duration reached "
                       f"({self.current_segment_duration:.2f}s >= {self.segment_duration}s)")

            ret = self._finish_segment()
            if ret != FlowReturn.OK:
                logger.error(f"    {self.name}.chain() - Failed to finish segment: {ret.name}")
                return ret

        # Return OK (we've buffered the data)
        logger.info(f"    {self.name}.chain() - Buffered, RETURNING OK to caller")
        return FlowReturn.OK

    def _add_to_segment(self, buffer: Buffer):
        """Add a buffer to the current segment"""
        if not self.current_segment:
            # First buffer in segment
            self.current_segment_start_time = buffer.pts

        self.current_segment.append(buffer)
        self.current_segment_duration += buffer.duration

        logger.debug(f"    {self.name} - Segment has {len(self.current_segment)} buffers, "
                    f"duration: {self.current_segment_duration:.2f}s")

    def _finish_segment(self) -> FlowReturn:
        """
        Finish current segment and push it downstream.

        Creates a single "segment" buffer containing all the accumulated data.
        """
        if not self.current_segment:
            return FlowReturn.OK

        # Create segment data
        segment_data = {
            "type": "hls_segment",
            "segment_number": self.segment_number,
            "duration": self.current_segment_duration,
            "buffer_count": len(self.current_segment),
            "start_pts": self.current_segment_start_time,
            "buffers": self.current_segment.copy(),  # All buffers in this segment
            "filename": f"segment_{self.segment_number:06d}.ts"  # Simulated filename
        }

        # Create segment buffer
        segment_buffer = Buffer(
            data=segment_data,
            pts=self.current_segment_start_time,
            duration=self.current_segment_duration,
            sequence=self.segment_number
        )

        logger.info(f"\n    {self.name} - SEGMENT COMPLETE!")
        logger.info(f"    Segment #{self.segment_number}: {len(self.current_segment)} buffers, "
                   f"{self.current_segment_duration:.2f}s")
        logger.info(f"    Pushing segment downstream...\n")

        # Push the segment downstream
        ret = self.src_pad.push(segment_buffer)

        # Reset for next segment
        self.segment_number += 1
        self.current_segment = []
        self.current_segment_duration = 0.0

        logger.info(f"    {self.name} - Segment push returned {ret.name}")

        return ret
