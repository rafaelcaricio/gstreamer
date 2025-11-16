"""
DataSource: Generates fake data in a separate thread

Like GstBaseSrc and specifically like videotestsrc or audiotestsrc,
this element:
- Has only a source pad (no sink pads)
- Runs a loop in a separate thread
- Calls gst_pad_push() to send buffers downstream
- Demonstrates how the call chain starts
"""

import threading
import time
import logging
from typing import Optional

from ..core import (
    Element, Buffer, BufferFlags, Pad, PadDirection,
    FlowReturn, State, StateChange, StateChangeReturn
)

logger = logging.getLogger(__name__)


class DataSource(Element):
    """
    Source element that generates fake data.

    This mimics how real GStreamer sources work:
    - Runs gst_base_src_loop() in a thread
    - Calls gst_pad_push() to send buffers downstream
    - The push() creates the entire call chain!
    """

    def __init__(self, name: str, data_rate: float = 1.0, max_buffers: int = -1):
        super().__init__(name)

        # Configuration
        self.data_rate = data_rate  # Buffers per second
        self.max_buffers = max_buffers  # -1 for infinite

        # State
        self.sequence = 0
        self.is_live = True  # Acts like a live source
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Create source pad (output)
        # Like GstBaseSrc creates its "src" pad
        self.src_pad = Pad("src", PadDirection.SRC, self)
        self.add_pad(self.src_pad)

    def change_state(self, transition: StateChange) -> StateChangeReturn:
        """
        Handle state changes.

        PAUSED -> PLAYING: Start the streaming thread
        PLAYING -> PAUSED: Stop the thread
        """
        logger.debug(f"{self.name} - change_state: {transition.name}")

        if transition == StateChange.PAUSED_TO_PLAYING:
            # Start streaming!
            logger.info(f"{self.name} - Starting streaming thread")
            self.running = True
            self.thread = threading.Thread(target=self._source_loop, daemon=True)
            self.thread.start()

            # Live sources return NO_PREROLL
            return StateChangeReturn.NO_PREROLL

        elif transition == StateChange.PLAYING_TO_PAUSED:
            # Stop streaming
            logger.info(f"{self.name} - Stopping streaming thread")
            self.running = False
            if self.thread:
                self.thread.join(timeout=2.0)
                self.thread = None
            return StateChangeReturn.SUCCESS

        # Let parent handle pad activation
        return super().change_state(transition)

    def _source_loop(self):
        """
        The streaming loop - THIS IS THE KEY!

        This is like gst_base_src_loop() from gstbasesrc.c:2881

        It runs in a separate thread and:
        1. Creates buffers with data
        2. Calls gst_pad_push() to send them downstream
        3. The push() triggers the entire call chain!
        """
        logger.info(f"{self.name} - Source loop STARTED")

        start_time = time.time()
        buffer_count = 0

        while self.running:
            # Check if we've hit max buffers
            if self.max_buffers >= 0 and buffer_count >= self.max_buffers:
                logger.info(f"{self.name} - Reached max_buffers ({self.max_buffers}), sending EOS")
                self._send_eos()
                break

            # Create a buffer with fake data
            current_time = time.time() - start_time
            buffer = self._create_buffer(current_time)

            # THIS IS THE KEY LINE!
            # gst_pad_push() starts the entire call chain through the pipeline
            logger.info(f"\n{self.name} - PUSHING buffer {buffer.sequence}")
            logger.info(f"{'*'*60}")

            ret = self.src_pad.push(buffer)

            logger.info(f"{'*'*60}")
            logger.info(f"{self.name} - PUSH RETURNED: {ret.name}\n")

            # Handle flow return
            if ret == FlowReturn.OK:
                buffer_count += 1
                self.sequence += 1

            elif ret == FlowReturn.EOS:
                logger.info(f"{self.name} - Got EOS, stopping")
                break

            elif ret in (FlowReturn.FLUSHING, FlowReturn.NOT_LINKED):
                logger.warning(f"{self.name} - Flow return: {ret.name}")
                time.sleep(0.1)
                continue

            else:
                logger.error(f"{self.name} - Error pushing buffer: {ret.name}")
                break

            # Rate limiting (simulate real-time data)
            sleep_time = 1.0 / self.data_rate
            time.sleep(sleep_time)

        logger.info(f"{self.name} - Source loop STOPPED")
        self.running = False

    def _create_buffer(self, timestamp: float) -> Buffer:
        """
        Create a buffer with fake data.

        In a real source, this would read from a file, camera, network, etc.
        Here we just create fake JSON data.
        """
        # Simulate some data (could be video frames, audio samples, etc.)
        data = {
            "type": "data_packet",
            "sequence": self.sequence,
            "timestamp": timestamp,
            "payload": f"Data from {self.name} at t={timestamp:.2f}s",
            "size": 1024  # Pretend it's 1KB
        }

        buffer = Buffer(
            data=data,
            pts=timestamp,
            duration=1.0 / self.data_rate,
            sequence=self.sequence,
            flags=BufferFlags.NONE
        )

        # Mark first buffer as DISCONT (discontinuity)
        if self.sequence == 0:
            buffer.set_flags(BufferFlags.DISCONT)

        return buffer

    def _send_eos(self):
        """
        Send End-Of-Stream.

        In real GStreamer, this would be gst_pad_push_event(EOS).
        For simplicity, we'll just send a buffer with EOS flag.
        """
        eos_buffer = Buffer(
            data={"type": "EOS"},
            pts=0.0,
            flags=BufferFlags.EOS
        )
        self.src_pad.push(eos_buffer)
