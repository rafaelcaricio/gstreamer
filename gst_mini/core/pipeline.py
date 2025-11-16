"""GstPipeline - Container for elements."""

import time
from typing import List

from .element import GstElement, GstState
from .clock import GstClock


class GstPipeline:
    """
    Pipeline manages a collection of linked elements.

    Similar to GstPipeline in GStreamer.
    """

    def __init__(self, name: str):
        """
        Create a pipeline.

        Args:
            name: Pipeline name
        """
        self.name = name
        self.elements: List[GstElement] = []
        self.clock = GstClock()
        self.base_time = 0.0
        self.state = GstState.NULL

    def add(self, *elements: GstElement):
        """
        Add elements to the pipeline.

        Args:
            *elements: Elements to add
        """
        for element in elements:
            self.elements.append(element)
            element.pipeline = self

    def link(self, src: GstElement, dst: GstElement):
        """
        Link two elements together.

        Args:
            src: Source element
            dst: Destination element
        """
        src.link(dst)

    def set_state(self, state: GstState):
        """
        Set the state of all elements in the pipeline.

        Args:
            state: Target state
        """
        print(f"[{self.clock.get_time():.3f}s] Pipeline: Setting state to {state.name}")

        # Special handling for PLAYING state
        if state == GstState.PLAYING and self.state != GstState.PLAYING:
            # Start the clock
            if self.clock._start_time is None:
                self.clock.start()

            # Set base_time (corresponds to base_time in gstbasesink.c:2350)
            # In a real pipeline, this synchronizes multiple sinks
            self.base_time = self.clock.get_time()
            print(f"[{self.clock.get_time():.3f}s] Pipeline: base_time set to {self.base_time:.3f}s")

        self.state = state

        # Propagate state change to all elements
        for element in self.elements:
            element.set_state(state)

    def run(self, duration: float = 30.0):
        """
        Run the pipeline for a specified duration.

        Args:
            duration: How long to run in seconds (default: 30s)
        """
        print(f"[{self.clock.get_time():.3f}s] Pipeline: Running for {duration}s...")

        try:
            # Set to PLAYING if not already
            if self.state != GstState.PLAYING:
                self.set_state(GstState.PLAYING)

            # Run for specified duration
            start = time.monotonic()
            while time.monotonic() - start < duration:
                time.sleep(0.1)

        except KeyboardInterrupt:
            print(f"\n[{self.clock.get_time():.3f}s] Pipeline: Interrupted by user")

        finally:
            # Clean shutdown
            print(f"[{self.clock.get_time():.3f}s] Pipeline: Stopping...")
            self.set_state(GstState.NULL)

    def get_position(self) -> float:
        """
        Get current pipeline position (running time).

        Returns:
            Current running time in seconds
        """
        if self.state == GstState.PLAYING:
            return self.clock.get_time() - self.base_time
        return 0.0

    def __repr__(self) -> str:
        return f"GstPipeline(name={self.name}, elements={len(self.elements)}, state={self.state.name})"
