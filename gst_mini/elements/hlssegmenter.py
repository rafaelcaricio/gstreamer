"""HLSSegmenter - Accumulates buffers into timed segments."""

from typing import List
from ..core.element import GstElement
from ..core.buffer import GstBuffer, BufferFlags
from ..core.pad import GstFlowReturn


class HLSSegmenter(GstElement):
    """
    Segmenter element that accumulates buffers into HLS-like segments.

    Demonstrates buffering strategy - collect frames for a target duration,
    then emit as a single segment buffer.
    """

    def __init__(self, name: str, target_duration: float = 6.0):
        """
        Create an HLS segmenter.

        Args:
            name: Element name
            target_duration: Target segment duration in seconds
        """
        super().__init__(name)
        self.target_duration = target_duration

        # Current segment being accumulated
        self.current_segment: List[GstBuffer] = []
        self.segment_start_pts = None
        self.segment_number = 0

        # Create pads
        self.sink_pad = self.create_sink_pad("sink")
        self.sink_pad.set_chain_function(self._chain)
        self.src_pad = self.create_src_pad("src")

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        """
        Chain function - receives individual frames and groups them into segments.

        Args:
            buffer: Incoming buffer

        Returns:
            GstFlowReturn status
        """
        # Handle EOS - flush remaining segment
        if buffer.has_flag(BufferFlags.EOS):
            if self.current_segment:
                self._emit_segment()
            # Forward EOS
            return self.src_pad.push(buffer)

        # Initialize segment start time
        if self.segment_start_pts is None:
            self.segment_start_pts = buffer.pts
            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Starting segment {self.segment_number}")

        # Add buffer to current segment
        self.current_segment.append(buffer)

        # Check if segment duration reached
        segment_duration = buffer.pts - self.segment_start_pts

        if segment_duration >= self.target_duration:
            # Emit complete segment
            self._emit_segment()

        return GstFlowReturn.OK

    def _emit_segment(self):
        """
        Emit the current segment as a single buffer.

        Creates a segment buffer containing all accumulated frames.
        """
        if not self.current_segment:
            return

        # Calculate segment metadata
        first_buffer = self.current_segment[0]
        last_buffer = self.current_segment[-1]

        segment_pts = first_buffer.pts
        segment_duration = (last_buffer.pts + last_buffer.duration) - first_buffer.pts
        num_frames = len(self.current_segment)

        # Create segment data
        segment_data = {
            'segment_num': self.segment_number,
            'buffers': self.current_segment.copy(),
            'duration': segment_duration,
            'num_frames': num_frames,
            'start_pts': segment_pts,
        }

        # Create segment buffer
        # Note: PTS is the start of the segment, duration is total segment length
        segment_buffer = GstBuffer(
            pts=segment_pts,
            duration=segment_duration,
            data=segment_data,
            flags=BufferFlags.SEGMENT
        )

        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Segment {self.segment_number} complete "
              f"({num_frames} frames, {segment_duration:.1f}s, PTS={segment_pts:.3f}s)")

        # Push segment downstream
        self.src_pad.push(segment_buffer)

        # Start new segment
        self.segment_number += 1
        self.current_segment = []
        self.segment_start_pts = None

    def on_null(self):
        """Called when going to NULL state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Total segments created: {self.segment_number}")
