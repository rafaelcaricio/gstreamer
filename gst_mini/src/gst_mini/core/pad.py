"""GstPad - Connection point for elements."""

import threading
from typing import Callable, Optional, TYPE_CHECKING
from enum import Enum, auto

from .buffer import GstBuffer

if TYPE_CHECKING:
    from .element import GstElement


class GstFlowReturn(Enum):
    """Return values for pad operations (similar to GstFlowReturn)."""
    OK = auto()
    EOS = auto()
    FLUSHING = auto()
    ERROR = auto()


class GstPad:
    """
    Simplified GstPad for connecting elements.

    Corresponds to gst_pad_push / gst_pad_chain_data_unchecked in gstpad.c:4497-4586
    """

    def __init__(self, name: str, element: 'GstElement'):
        """
        Create a pad.

        Args:
            name: Pad name (e.g., "src", "sink")
            element: Parent element
        """
        self.name = name
        self.element = element
        self.peer: Optional['GstPad'] = None
        self.chain_function: Optional[Callable[[GstBuffer], GstFlowReturn]] = None

        # Thread safety - similar to GST_PAD_STREAM_LOCK
        self._lock = threading.Lock()
        self._flushing = False

    def link(self, peer_pad: 'GstPad'):
        """
        Link this pad to a peer pad.

        Args:
            peer_pad: The pad to link to
        """
        self.peer = peer_pad
        peer_pad.peer = self

    def set_chain_function(self, func: Callable[[GstBuffer], GstFlowReturn]):
        """
        Set the chain function for this pad.

        Args:
            func: Function to call when receiving buffers
        """
        self.chain_function = func

    def push(self, buffer: GstBuffer) -> GstFlowReturn:
        """
        Push a buffer to the peer pad.

        This is similar to gst_pad_push() in gstpad.c:4795

        Args:
            buffer: Buffer to push

        Returns:
            GstFlowReturn indicating success/failure
        """
        if self.peer is None:
            return GstFlowReturn.ERROR

        # Call peer's chain function - this is the synchronous call
        # that makes chain calls blocking (gstpad.c:4560)
        return self.peer._chain(buffer)

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        """
        Internal chain function handler.

        Similar to gst_pad_chain_data_unchecked in gstpad.c:4497

        Args:
            buffer: Buffer received

        Returns:
            GstFlowReturn from the chain function
        """
        # Acquire stream lock (GST_PAD_STREAM_LOCK at gstpad.c:4509)
        with self._lock:
            if self._flushing:
                return GstFlowReturn.FLUSHING

            if self.chain_function is None:
                return GstFlowReturn.ERROR

            # Call the element's chain function (gstpad.c:4560)
            return self.chain_function(buffer)

    def set_flushing(self, flushing: bool):
        """Set the flushing state of the pad."""
        with self._lock:
            self._flushing = flushing

    def __repr__(self) -> str:
        peer_name = f"{self.peer.element.name}:{self.peer.name}" if self.peer else "unlinked"
        return f"GstPad({self.element.name}:{self.name} -> {peer_name})"
