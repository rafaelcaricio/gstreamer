"""GstElement - Base class for pipeline elements."""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Optional

from .pad import GstPad
from .segment import GstSegment


class GstState(Enum):
    """Element states (simplified version of GstState)."""
    NULL = auto()
    READY = auto()
    PAUSED = auto()
    PLAYING = auto()


class GstElement(ABC):
    """
    Base class for all pipeline elements.

    Elements are the processing units in a pipeline.
    """

    def __init__(self, name: str):
        """
        Create an element.

        Args:
            name: Element name
        """
        self.name = name
        self.state = GstState.NULL
        self.src_pad: Optional[GstPad] = None
        self.sink_pad: Optional[GstPad] = None
        self.segment = GstSegment()
        self.pipeline: Optional['GstElement'] = None  # Will be set by pipeline

    def create_src_pad(self, name: str = "src") -> GstPad:
        """
        Create a source pad.

        Args:
            name: Pad name

        Returns:
            Created source pad
        """
        self.src_pad = GstPad(name, self)
        return self.src_pad

    def create_sink_pad(self, name: str = "sink") -> GstPad:
        """
        Create a sink pad with chain function.

        Args:
            name: Pad name

        Returns:
            Created sink pad
        """
        self.sink_pad = GstPad(name, self)
        return self.sink_pad

    def link(self, downstream: 'GstElement'):
        """
        Link this element to a downstream element.

        Args:
            downstream: Element to link to
        """
        if self.src_pad is None:
            raise ValueError(f"{self.name} has no source pad")
        if downstream.sink_pad is None:
            raise ValueError(f"{downstream.name} has no sink pad")

        self.src_pad.link(downstream.sink_pad)

    def set_state(self, state: GstState):
        """
        Change element state.

        Args:
            state: New state
        """
        if self.state == state:
            return

        old_state = self.state

        # Handle direct jumps (e.g., NULL -> PLAYING)
        # Go through intermediate states
        if old_state == GstState.NULL and state == GstState.PLAYING:
            self.set_state(GstState.READY)
            self.set_state(GstState.PAUSED)
            self.set_state(GstState.PLAYING)
            return
        elif old_state == GstState.NULL and state == GstState.PAUSED:
            self.set_state(GstState.READY)
            self.set_state(GstState.PAUSED)
            return

        self.state = state

        # Call subclass handlers
        if state == GstState.READY and old_state == GstState.NULL:
            self.on_ready()
        elif state == GstState.PAUSED and old_state == GstState.READY:
            self.on_paused()
        elif state == GstState.PLAYING and old_state == GstState.PAUSED:
            self.on_playing()
        elif state == GstState.PAUSED and old_state == GstState.PLAYING:
            self.on_paused_from_playing()
        elif state == GstState.NULL:
            self.on_null()

    # State change hooks (can be overridden by subclasses)
    def on_ready(self):
        """Called when transitioning to READY state."""
        pass

    def on_paused(self):
        """Called when transitioning to PAUSED state."""
        pass

    def on_playing(self):
        """Called when transitioning to PLAYING state."""
        pass

    def on_paused_from_playing(self):
        """Called when transitioning from PLAYING to PAUSED."""
        pass

    def on_null(self):
        """Called when transitioning to NULL state."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, state={self.state.name})"
