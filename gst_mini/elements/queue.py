"""Queue - Thread decoupling element."""

import threading
from collections import deque
from typing import Optional

from ..core.element import GstElement, GstState
from ..core.buffer import GstBuffer, BufferFlags
from ..core.pad import GstFlowReturn


class Queue(GstElement):
    """
    Queue element for thread decoupling.

    Demonstrates the critical role of queues in live pipelines:
    - Chain function runs in upstream thread (enqueues)
    - Loop function runs in separate thread (dequeues and pushes)

    Corresponds to gstqueue.c:1271-1639
    """

    def __init__(self, name: str, max_size: int = 10, leaky: Optional[str] = None):
        """
        Create a queue.

        Args:
            name: Element name
            max_size: Maximum number of buffers to hold
            leaky: Leaky mode - "upstream", "downstream", or None
                   - "upstream": drop new incoming buffers when full
                   - "downstream": drop old buffers when full
                   - None: block upstream when full
        """
        super().__init__(name)
        self.max_size = max_size
        self.leaky = leaky

        # Internal queue
        self._queue = deque()

        # Thread synchronization
        self._mutex = threading.Lock()
        self._not_empty = threading.Condition(self._mutex)
        self._not_full = threading.Condition(self._mutex)

        # Loop thread
        self._loop_thread = None
        self._running = False

        # Statistics
        self.buffers_in = 0
        self.buffers_out = 0
        self.buffers_dropped = 0
        self._discont_pending = False
        self._was_empty = True  # Track state for logging

        # Create pads
        self.sink_pad = self.create_sink_pad("sink")
        self.sink_pad.set_chain_function(self._chain)
        self.src_pad = self.create_src_pad("src")

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        """
        Chain function - called by upstream element.

        This runs in the UPSTREAM thread (e.g., LiveSource thread).
        Corresponds to gst_queue_chain_buffer_or_list in gstqueue.c:1271

        Args:
            buffer: Incoming buffer

        Returns:
            GstFlowReturn status
        """
        with self._mutex:
            # Check if EOS
            if buffer.has_flag(BufferFlags.EOS):
                self._queue.append(buffer)
                self._not_empty.notify()
                return GstFlowReturn.EOS

            # Check if queue is full
            while len(self._queue) >= self.max_size:
                if self.leaky == "upstream":
                    # Drop this new buffer (gstqueue.c:1304-1311)
                    self._discont_pending = True
                    self.buffers_dropped += 1
                    return GstFlowReturn.OK

                elif self.leaky == "downstream":
                    # Drop oldest buffer (gstqueue.c:1312-1320)
                    if self._queue:
                        dropped = self._queue.popleft()
                        self.buffers_dropped += 1
                        self._discont_pending = True
                    break

                else:
                    # Block until space available (gstqueue.c:1325-1334)
                    # This is where upstream gets blocked!
                    self._not_full.wait()

            # Mark buffer with DISCONT flag if we dropped buffers
            # Corresponds to gstqueue.c:1348-1368
            if self._discont_pending:
                buffer.set_flag(BufferFlags.DISCONT)
                self._discont_pending = False

            # Enqueue the buffer (gstqueue.c:1375)
            self._queue.append(buffer)
            self.buffers_in += 1

            current_size = len(self._queue)

            # Notify loop thread that data is available
            self._not_empty.notify()

        # Log when queue fills up (outside mutex)
        if current_size == self.max_size:
            print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Queue FULL ({current_size}/{self.max_size})")

        return GstFlowReturn.OK

    def on_playing(self):
        """Start the loop thread when entering PLAYING state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Starting loop thread (max_size={self.max_size}, leaky={self.leaky})")

        self._running = True
        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()

    def on_null(self):
        """Stop the loop thread when entering NULL state."""
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Stopping loop thread")
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Stats - In: {self.buffers_in}, Out: {self.buffers_out}, Dropped: {self.buffers_dropped}")

        self._running = False

        # Wake up loop thread if it's waiting
        with self._mutex:
            self._not_empty.notify()

        if self._loop_thread is not None:
            self._loop_thread.join(timeout=1.0)

    def _loop(self):
        """
        Loop function - runs in separate thread.

        This is the DOWNSTREAM thread that pulls buffers and pushes them.
        Corresponds to gst_queue_loop in gstqueue.c:1590

        This is where clock waits happen (in downstream element's chain function),
        so the upstream thread never blocks on synchronization!
        """
        while self._running:
            buffer = None

            # Wait for buffer to be available
            with self._mutex:
                while self._running and len(self._queue) == 0:
                    # Queue is empty, wait (gstqueue.c:1609-1611)
                    self._not_empty.wait(timeout=0.1)

                if not self._running:
                    break

                if len(self._queue) > 0:
                    # Dequeue buffer (gstqueue.c:1624)
                    buffer = self._queue.popleft()
                    self.buffers_out += 1

                    current_size = len(self._queue)

                    # Notify chain function that space is available
                    self._not_full.notify()

            # Push buffer downstream (outside mutex to avoid deadlock)
            # This may block on clock waits in sink!
            if buffer is not None:
                # Only log when transitioning to empty state
                if current_size == 0 and not self._was_empty:
                    print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Queue EMPTY")
                    self._was_empty = True
                elif current_size > 0:
                    self._was_empty = False

                # This is the key: push happens outside the mutex
                # So upstream can continue enqueueing while we're blocked here
                result = self.src_pad.push(buffer)

                if result == GstFlowReturn.EOS:
                    break

    def get_current_level(self) -> int:
        """Get current number of buffers in queue."""
        with self._mutex:
            return len(self._queue)

    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            'buffers_in': self.buffers_in,
            'buffers_out': self.buffers_out,
            'buffers_dropped': self.buffers_dropped,
            'current_level': self.get_current_level(),
            'max_size': self.max_size,
        }
