"""S3Sink - Uploads segments with synchronization."""

import time
from ..core.element import GstElement
from ..core.buffer import GstBuffer, BufferFlags
from ..core.pad import GstFlowReturn


class S3Sink(GstElement):
    """
    Sink element that simulates S3 upload with synchronization.

    Demonstrates gst_base_sink_do_sync and gst_base_sink_wait_clock
    from gstbasesink.c:2665-2828 and gstbasesink.c:2333-2404
    """

    def __init__(self, name: str, bucket: str = "my-bucket", sync: bool = True):
        """
        Create an S3 sink.

        Args:
            name: Element name
            bucket: S3 bucket name (simulated)
            sync: Enable synchronization to clock
        """
        super().__init__(name)
        self.bucket = bucket
        self.sync = sync
        self.last_rendered_pts = 0.0
        self.segment_count = 0

        # Create sink pad and set chain function
        self.sink_pad = self.create_sink_pad("sink")
        self.sink_pad.set_chain_function(self._chain)

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        """
        Chain function - receives buffers from upstream.

        This is where synchronization happens (similar to gst_base_sink_do_sync).

        Args:
            buffer: Incoming buffer

        Returns:
            GstFlowReturn status
        """
        # Check for EOS
        if buffer.has_flag(BufferFlags.EOS):
            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Received EOS")
            return GstFlowReturn.EOS

        # Extract timestamp
        pts = buffer.pts

        # Convert stream time to running time (gst_segment_to_running_time)
        # Corresponds to gstbasesink.c:2207
        running_time = self.segment.to_running_time(pts)

        if running_time < 0:
            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Buffer outside segment, dropping")
            return GstFlowReturn.OK

        # Synchronization (gst_base_sink_do_sync)
        if self.sync and self.state.name == 'PLAYING':
            # Calculate clock time: running_time + base_time
            # Corresponds to gstbasesink.c:2356
            clock_time = running_time + self.pipeline.base_time

            current_time = self.pipeline.clock.get_time()

            # Wait on clock (gst_base_sink_wait_clock at gstbasesink.c:2381)
            print(f"[{current_time:.3f}s] {self.name}: Waiting for clock_time={clock_time:.3f}s...")

            clock_return, jitter = self.pipeline.clock.wait_until(clock_time)

            actual_time = self.pipeline.clock.get_time()
            jitter_ms = jitter * 1000

            if jitter >= 0:
                print(f"[{actual_time:.3f}s] {self.name}: Clock wait complete (jitter: {jitter_ms:+.1f}ms)")
            else:
                print(f"[{actual_time:.3f}s] {self.name}: Buffer late (jitter: {jitter_ms:+.1f}ms)")

        # Simulate S3 upload (the "render" vmethod)
        self._upload_segment(buffer)

        # Update position
        self.last_rendered_pts = pts

        return GstFlowReturn.OK

    def _upload_segment(self, buffer: GstBuffer):
        """
        Simulate uploading a segment to S3.

        Args:
            buffer: Buffer containing segment data
        """
        segment_data = buffer.data

        if isinstance(segment_data, dict) and 'segment_num' in segment_data:
            # This is a segment buffer
            segment_num = segment_data['segment_num']
            num_frames = len(segment_data['buffers'])
            duration = segment_data['duration']

            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Uploading segment_{segment_num}.cmfv "
                  f"({num_frames} frames, {duration:.1f}s) to s3://{self.bucket}/")

            # Simulate upload delay
            time.sleep(0.017)  # 17ms simulated upload time

            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Upload complete")
            self.segment_count += 1

        else:
            # Regular buffer
            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Processing buffer at PTS={buffer.pts:.3f}s")

    def get_position(self) -> float:
        """Get current playback position."""
        return self.last_rendered_pts

    def on_null(self):
        """Called when going to NULL state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Total segments uploaded: {self.segment_count}")
