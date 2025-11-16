"""LiveSource - Simulates live camera generating frames."""

import threading
import time
from ..core.element import GstElement, GstState
from ..core.buffer import GstBuffer, BufferFlags
from ..core.pad import GstFlowReturn


class LiveSource(GstElement):
    """
    Source element that generates frames at a fixed rate (like a camera).

    Demonstrates live sources that cannot be paused - they keep generating data.
    """

    def __init__(self, name: str, fps: int = 30):
        """
        Create a live source.

        Args:
            name: Element name
            fps: Frames per second to generate
        """
        super().__init__(name)
        self.fps = fps
        self.frame_interval = 1.0 / fps  # Time between frames
        self.frame_count = 0
        self.dropped_frames = 0

        self._thread = None
        self._running = False
        self._start_time = None

        # Create source pad
        self.src_pad = self.create_src_pad("src")

    def on_playing(self):
        """Start generating frames when entering PLAYING state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Starting frame generation at {self.fps} fps")

        self._running = True
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._generate_frames, daemon=True)
        self._thread.start()

    def on_null(self):
        """Stop generating frames when entering NULL state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Stopping frame generation")
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Generated {self.frame_count} frames, "
              f"dropped {self.dropped_frames} frames")

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _generate_frames(self):
        """
        Frame generation loop (runs in separate thread).

        This simulates a live camera that captures frames at regular intervals.
        """
        next_frame_time = time.monotonic()

        while self._running:
            current_time = time.monotonic()

            # Check if it's time for the next frame
            if current_time >= next_frame_time:
                # Calculate PTS (presentation timestamp)
                # This is the time since we started, in seconds
                pts = current_time - self._start_time
                duration = self.frame_interval

                # Create buffer with frame data
                buffer = GstBuffer(
                    pts=pts,
                    duration=duration,
                    data={
                        'frame': self.frame_count,
                        'timestamp': pts,
                        'content': f'frame_{self.frame_count:06d}'
                    }
                )

                # Try to push buffer downstream
                # This call may block if downstream is slow or queue is full
                result = self.src_pad.push(buffer)

                if result == GstFlowReturn.OK:
                    if self.frame_count % 30 == 0:  # Log every second
                        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Generated frame {self.frame_count}, PTS={pts:.3f}s")
                    self.frame_count += 1
                else:
                    # Push failed (queue full, flushing, etc.)
                    self.dropped_frames += 1
                    if self.dropped_frames % 10 == 1:
                        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Dropped frame {self.frame_count} (total dropped: {self.dropped_frames})")

                # Schedule next frame
                next_frame_time += self.frame_interval

            else:
                # Sleep until next frame time
                sleep_time = next_frame_time - current_time
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.001))  # Sleep in small increments

        # Send EOS when stopping
        eos_buffer = GstBuffer(pts=0.0, duration=0.0, data={}, flags=BufferFlags.EOS)
        self.src_pad.push(eos_buffer)

    def get_stats(self) -> dict:
        """Get statistics about frame generation."""
        return {
            'frames_generated': self.frame_count,
            'frames_dropped': self.dropped_frames,
            'fps': self.fps,
        }
