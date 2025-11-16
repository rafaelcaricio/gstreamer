"""
Element: Base class for all pipeline components

Elements are the processing units in GStreamer.
They have pads, can change state, and process data.
"""

from enum import Enum, auto
from typing import List, Optional
import logging

from .pad import Pad, PadDirection, PadMode, PadLinkReturn

logger = logging.getLogger(__name__)


class State(Enum):
    """
    Element states (like GstState).

    State transitions happen in order:
    NULL -> READY -> PAUSED -> PLAYING
    """
    NULL = 0       # Initial state, no resources allocated
    READY = 1      # Resources allocated, ready to process
    PAUSED = 2     # Pads activated, ready to stream (paused)
    PLAYING = 3    # Actively streaming data


class StateChangeReturn(Enum):
    """Return values from state changes (like GstStateChangeReturn)"""
    FAILURE = 0    # State change failed
    SUCCESS = 1    # State change succeeded
    ASYNC = 2      # State change will complete asynchronously
    NO_PREROLL = 3 # Success, but element cannot preroll (live sources)


class StateChange(Enum):
    """
    State transitions (like GstStateChange).
    Format: CURRENT_TO_NEXT
    """
    NULL_TO_READY = auto()
    READY_TO_PAUSED = auto()
    PAUSED_TO_PLAYING = auto()
    PLAYING_TO_PAUSED = auto()
    PAUSED_TO_READY = auto()
    READY_TO_NULL = auto()


class Element:
    """
    Base class for all elements.

    Like GstElement, this provides:
    - Pad management
    - State management
    - Linking helpers
    """

    def __init__(self, name: str):
        self.name = name
        self.state = State.NULL
        self.pads: List[Pad] = []

    def add_pad(self, pad: Pad) -> bool:
        """
        Add a pad to this element.

        Like gst_element_add_pad() in GStreamer.
        """
        if pad.parent is not None and pad.parent != self:
            logger.error(f"{self.name} - Pad {pad.name} already has a parent")
            return False

        pad.parent = self
        self.pads.append(pad)
        logger.debug(f"{self.name} - Added pad: {pad.name} ({pad.direction.name})")
        return True

    def get_pad(self, name: str) -> Optional[Pad]:
        """Get a pad by name"""
        for pad in self.pads:
            if pad.name == name:
                return pad
        return None

    def get_src_pad(self) -> Optional[Pad]:
        """Get the (first) source pad"""
        for pad in self.pads:
            if pad.direction == PadDirection.SRC:
                return pad
        return None

    def get_sink_pad(self) -> Optional[Pad]:
        """Get the (first) sink pad"""
        for pad in self.pads:
            if pad.direction == PadDirection.SINK:
                return pad
        return None

    def link(self, other: 'Element') -> bool:
        """
        Link this element to another element.

        Like gst_element_link() in GStreamer.
        Finds compatible pads and links them.
        """
        # Get source pad from this element
        src_pad = self.get_src_pad()
        if src_pad is None:
            logger.error(f"{self.name} - No source pad found")
            return False

        # Get sink pad from other element
        sink_pad = other.get_sink_pad()
        if sink_pad is None:
            logger.error(f"{other.name} - No sink pad found")
            return False

        # Link the pads
        result = src_pad.link(sink_pad)
        if result == PadLinkReturn.OK:
            logger.info(f"ELEMENT LINK: {self.name} -> {other.name}")
            return True

        logger.error(f"Failed to link {self.name} -> {other.name}: {result.name}")
        return False

    def set_state(self, new_state: State) -> StateChangeReturn:
        """
        Change element state.

        Like gst_element_set_state() in GStreamer.
        Calls change_state() to do the actual work.
        """
        if new_state == self.state:
            logger.debug(f"{self.name} - Already in {new_state.name} state")
            return StateChangeReturn.SUCCESS

        current = self.state
        logger.info(f"{self.name} - State change: {current.name} -> {new_state.name}")

        # Determine the transition
        transition = self._get_transition(current, new_state)
        if transition is None:
            logger.error(f"{self.name} - Invalid state transition")
            return StateChangeReturn.FAILURE

        # Perform the state change
        ret = self.change_state(transition)

        if ret in (StateChangeReturn.SUCCESS, StateChangeReturn.NO_PREROLL):
            self.state = new_state
            logger.info(f"{self.name} - State change SUCCESS: now in {new_state.name}")
        else:
            logger.error(f"{self.name} - State change FAILED")

        return ret

    def change_state(self, transition: StateChange) -> StateChangeReturn:
        """
        Override this to handle state changes.

        Like GstElement::change_state vfunc in GStreamer.
        This is where elements allocate resources, activate pads, etc.
        """
        # Default implementation handles pad activation
        if transition == StateChange.READY_TO_PAUSED:
            # Activate all pads
            return self._activate_pads(True)

        elif transition == StateChange.PAUSED_TO_READY:
            # Deactivate all pads
            return self._activate_pads(False)

        return StateChangeReturn.SUCCESS

    def _activate_pads(self, activate: bool) -> StateChangeReturn:
        """
        Activate or deactivate all pads.

        Like gst_element_pads_activate() from gstelement.c:3212
        """
        mode = PadMode.PUSH if activate else PadMode.NONE
        action = "Activating" if activate else "Deactivating"

        logger.debug(f"{self.name} - {action} pads")

        # Activate source pads first (like GStreamer does)
        for pad in self.pads:
            if pad.direction == PadDirection.SRC:
                if not pad.activate(mode):
                    logger.error(f"{self.name} - Failed to {action.lower()} pad {pad.name}")
                    return StateChangeReturn.FAILURE

        # Then sink pads
        for pad in self.pads:
            if pad.direction == PadDirection.SINK:
                if not pad.activate(mode):
                    logger.error(f"{self.name} - Failed to {action.lower()} pad {pad.name}")
                    return StateChangeReturn.FAILURE

        return StateChangeReturn.SUCCESS

    def _get_transition(self, current: State, target: State) -> Optional[StateChange]:
        """Map current and target states to a transition"""
        transitions = {
            (State.NULL, State.READY): StateChange.NULL_TO_READY,
            (State.READY, State.PAUSED): StateChange.READY_TO_PAUSED,
            (State.PAUSED, State.PLAYING): StateChange.PAUSED_TO_PLAYING,
            (State.PLAYING, State.PAUSED): StateChange.PLAYING_TO_PAUSED,
            (State.PAUSED, State.READY): StateChange.PAUSED_TO_READY,
            (State.READY, State.NULL): StateChange.READY_TO_NULL,
        }
        return transitions.get((current, target))

    def __repr__(self) -> str:
        return f"Element({self.name}, state={self.state.name}, pads={len(self.pads)})"
