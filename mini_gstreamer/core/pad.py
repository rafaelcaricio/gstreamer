"""
Pad: Connection point between elements

This is the CORE of how GStreamer works!
Pads are linked together, and when you call push() on a source pad,
it directly calls the chain function on the peer sink pad.

This creates the synchronous call stack we discussed.
"""

from enum import Enum, auto
from typing import Callable, Optional, TYPE_CHECKING
import logging
import threading

if TYPE_CHECKING:
    from .element import Element
    from .buffer import Buffer

logger = logging.getLogger(__name__)


class PadDirection(Enum):
    """Direction of data flow (like GstPadDirection)"""
    UNKNOWN = auto()
    SRC = auto()      # Source pad (outputs data)
    SINK = auto()     # Sink pad (receives data)


class PadMode(Enum):
    """Activation mode (like GstPadMode)"""
    NONE = auto()     # Pad is not active
    PUSH = auto()     # Push mode (source pushes to sink)
    PULL = auto()     # Pull mode (sink pulls from source)


class FlowReturn(Enum):
    """
    Return values from pad operations (like GstFlowReturn).
    These bubble up the call stack!
    """
    # Success codes
    OK = 0

    # Expected failures
    NOT_LINKED = -1      # Pad has no peer
    FLUSHING = -2        # Pad is flushing
    EOS = -3             # End of stream
    NOT_NEGOTIATED = -4  # Caps not negotiated

    # Errors
    ERROR = -5           # Generic error
    NOT_SUPPORTED = -6   # Operation not supported


class PadLinkReturn(Enum):
    """Return values from pad linking (like GstPadLinkReturn)"""
    OK = 0
    WRONG_DIRECTION = -1  # Can't link two source or two sink pads
    WAS_LINKED = -2       # Pad already linked
    REFUSED = -3          # Link refused


# Type alias for chain function
# This is THE KEY function pointer that gets called!
ChainFunction = Callable[['Pad', 'Buffer'], FlowReturn]


class Pad:
    """
    A Pad is a connection point on an Element.

    The magic happens here:
    - When you call push() on a SOURCE pad...
    - It finds the linked SINK pad...
    - And directly calls that pad's chain_function!

    This creates the synchronous call chain through the pipeline.
    """

    def __init__(self, name: str, direction: PadDirection, parent: Optional['Element'] = None):
        self.name = name
        self.direction = direction
        self.parent = parent
        self.peer: Optional['Pad'] = None
        self.mode = PadMode.NONE

        # THE KEY: Function pointer that gets called when data arrives!
        # In real GStreamer: GST_PAD_CHAINFUNC(pad)
        self._chain_function: Optional[ChainFunction] = None

        # State
        self._flushing = False
        self._eos = False
        self._active = False

        # Stream lock (ensures only one buffer flows through at a time)
        # In real GStreamer: GST_PAD_STREAM_LOCK
        self._stream_lock = threading.RLock()

    def set_chain_function(self, func: ChainFunction) -> None:
        """
        Set the chain function for this pad.

        This is like gst_pad_set_chain_function() in GStreamer.
        Elements call this to register their processing function.
        """
        if self.direction != PadDirection.SINK:
            raise ValueError("Can only set chain function on SINK pads")
        self._chain_function = func
        logger.debug(f"{self.parent.name if self.parent else ''}:{self.name} - "
                    f"Chain function set to {func.__name__}")

    def link(self, sink_pad: 'Pad') -> PadLinkReturn:
        """
        Link this source pad to a sink pad.

        Like gst_pad_link() in GStreamer.
        After linking, calling push() on this pad will call
        the peer pad's chain function.
        """
        # Validation
        if self.direction != PadDirection.SRC:
            logger.error(f"{self.get_name()} - Can only link from SOURCE pads")
            return PadLinkReturn.WRONG_DIRECTION

        if sink_pad.direction != PadDirection.SINK:
            logger.error(f"Can only link to SINK pads")
            return PadLinkReturn.WRONG_DIRECTION

        if self.peer is not None:
            logger.error(f"{self.get_name()} - Pad already linked")
            return PadLinkReturn.WAS_LINKED

        if sink_pad.peer is not None:
            logger.error(f"{sink_pad.get_name()} - Sink pad already linked")
            return PadLinkReturn.WAS_LINKED

        # Link the pads
        self.peer = sink_pad
        sink_pad.peer = self

        logger.info(f"LINKED: {self.get_name()} -> {sink_pad.get_name()}")
        return PadLinkReturn.OK

    def unlink(self) -> bool:
        """Unlink this pad from its peer"""
        if self.peer is None:
            return True

        peer = self.peer
        self.peer = None
        peer.peer = None

        logger.info(f"UNLINKED: {self.get_name()} -X- {peer.get_name()}")
        return True

    def push(self, buffer: 'Buffer') -> FlowReturn:
        """
        Push a buffer downstream.

        THIS IS THE KEY FUNCTION!

        Like gst_pad_push() in GStreamer, this:
        1. Checks if pad is valid for pushing
        2. Finds the peer pad
        3. Directly calls the peer's chain function
        4. Returns the result

        This creates the synchronous call stack!
        """
        if self.direction != PadDirection.SRC:
            logger.error(f"{self.get_name()} - Can only push from SOURCE pads")
            return FlowReturn.ERROR

        # Check state
        if self._flushing:
            logger.debug(f"{self.get_name()} - Pad is flushing")
            return FlowReturn.FLUSHING

        if self._eos:
            logger.debug(f"{self.get_name()} - Pad is EOS")
            return FlowReturn.EOS

        # Check if we have a peer
        if self.peer is None:
            logger.warning(f"{self.get_name()} - Not linked!")
            return FlowReturn.NOT_LINKED

        # Log the push (indent shows call depth)
        indent = "  " * self._get_call_depth()
        logger.debug(f"{indent}PUSH: {self.get_name()} -> {self.peer.get_name()} | {buffer}")

        # THE MAGIC HAPPENS HERE!
        # We directly call the peer's chain function.
        # This is exactly like gst_pad_chain_data_unchecked() in GStreamer.
        ret = self._chain_on_peer(buffer)

        logger.debug(f"{indent}PUSH RETURNED: {ret.name}")
        return ret

    def _chain_on_peer(self, buffer: 'Buffer') -> FlowReturn:
        """
        Call the chain function on the peer pad.

        This mimics gst_pad_chain_data_unchecked() from gstpad.c
        """
        peer = self.peer

        # Acquire stream lock (only one buffer at a time)
        # This is GST_PAD_STREAM_LOCK in real GStreamer
        with peer._stream_lock:
            # Check peer state
            if peer._flushing:
                return FlowReturn.FLUSHING

            if peer._eos:
                return FlowReturn.EOS

            if peer.mode != PadMode.PUSH:
                logger.error(f"{peer.get_name()} - Pad not in PUSH mode")
                return FlowReturn.ERROR

            # Get the chain function
            # This is like: chainfunc = GST_PAD_CHAINFUNC(pad)
            chain_func = peer._chain_function

            if chain_func is None:
                logger.error(f"{peer.get_name()} - No chain function set!")
                return FlowReturn.ERROR

            # DIRECT FUNCTION CALL!
            # This is the synchronous call that creates the call stack
            # In gstpad.c: ret = chainfunc(pad, parent, buffer)
            indent = "  " * self._get_call_depth()
            logger.debug(f"{indent}CALLING: {peer.parent.name if peer.parent else ''}."
                        f"{chain_func.__name__}()")

            ret = chain_func(peer, buffer)

            logger.debug(f"{indent}RETURNED: {ret.name}")
            return ret

    def activate(self, mode: PadMode) -> bool:
        """
        Activate the pad in a specific mode.

        Like gst_pad_activate_mode() in GStreamer.
        Called during READY -> PAUSED state transition.
        """
        if mode == PadMode.NONE:
            self._active = False
            self.mode = PadMode.NONE
            logger.debug(f"{self.get_name()} - Deactivated")
            return True

        if self.direction == PadDirection.SINK and self._chain_function is None:
            logger.error(f"{self.get_name()} - Cannot activate SINK pad without chain function")
            return False

        self._active = True
        self.mode = mode
        logger.debug(f"{self.get_name()} - Activated in {mode.name} mode")
        return True

    def set_flushing(self, flushing: bool) -> None:
        """Set flushing state (blocks data flow)"""
        self._flushing = flushing

    def set_eos(self, eos: bool) -> None:
        """Set EOS state"""
        self._eos = eos

    def get_name(self) -> str:
        """Get full pad name including parent element"""
        if self.parent:
            return f"{self.parent.name}:{self.name}"
        return self.name

    def _get_call_depth(self) -> int:
        """
        Get current call stack depth (for logging indentation).
        Helps visualize the call chain!
        """
        import traceback
        stack = traceback.extract_stack()
        # Count how many times we're in push/chain functions
        depth = sum(1 for frame in stack if 'push' in frame.name or 'chain' in frame.name)
        return depth // 2  # Divide by 2 since push calls chain

    def __repr__(self) -> str:
        peer_name = self.peer.get_name() if self.peer else "not-linked"
        return f"Pad({self.get_name()}, {self.direction.name}, peer={peer_name})"
