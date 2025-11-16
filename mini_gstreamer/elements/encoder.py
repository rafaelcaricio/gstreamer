"""
Encoder: Transform element that "encodes" data

Like GstBaseTransform and specifically like x264enc or vp8enc,
this element:
- Has both sink and source pads
- Receives buffers via chain function
- Transforms the data
- Pushes transformed buffers downstream

This demonstrates the synchronous call chain!
"""

import logging
from typing import Optional

from ..core import (
    Element, Buffer, BufferFlags, Pad, PadDirection, FlowReturn,
    State, StateChange, StateChangeReturn
)

logger = logging.getLogger(__name__)


class Encoder(Element):
    """
    Transform element that "encodes" data.

    This mimics GstBaseTransform's chain function pattern:
    - Receives buffer in chain function (on sink pad)
    - Processes/transforms the data
    - Pushes output buffer downstream (from source pad)

    The key: this is all SYNCHRONOUS - a direct call chain!
    """

    def __init__(self, name: str, codec: str = "h264"):
        super().__init__(name)

        self.codec = codec  # Simulated codec (h264, vp8, etc.)
        self.frame_count = 0

        # Create sink pad (input)
        self.sink_pad = Pad("sink", PadDirection.SINK, self)
        self.add_pad(self.sink_pad)

        # Create source pad (output)
        self.src_pad = Pad("src", PadDirection.SRC, self)
        self.add_pad(self.src_pad)

        # THE KEY: Register our chain function on the sink pad!
        # This is like:
        #   gst_pad_set_chain_function(trans->sinkpad, gst_base_transform_chain)
        # from gstbasetransform.c:391-392
        self.sink_pad.set_chain_function(self._chain)

    def _chain(self, pad: Pad, buffer: Buffer) -> FlowReturn:
        """
        Chain function - THE HEART OF THE ELEMENT!

        This is like gst_base_transform_chain() from gstbasetransform.c:2317

        When called:
        1. We receive a buffer
        2. We transform it (encode it)
        3. We push the result downstream via gst_pad_push()
        4. That push() calls the NEXT element's chain function
        5. When it returns, we return to OUR caller

        This creates a beautiful synchronous call stack!
        """
        logger.info(f"  {self.name}.chain() - RECEIVED {buffer}")

        # Check for EOS
        if buffer.has_flags(BufferFlags.EOS):
            logger.info(f"  {self.name}.chain() - Got EOS, passing through")
            return self.src_pad.push(buffer)

        # "Encode" the data (simulate processing)
        encoded_buffer = self._encode(buffer)

        # PUSH DOWNSTREAM!
        # This is the key gst_pad_push() call that continues the chain
        logger.info(f"  {self.name}.chain() - PUSHING encoded buffer downstream")
        ret = self.src_pad.push(encoded_buffer)

        logger.info(f"  {self.name}.chain() - Push returned {ret.name}, RETURNING to caller")

        # Return the flow result back up the stack
        return ret

    def _encode(self, buffer: Buffer) -> Buffer:
        """
        Simulate encoding the buffer.

        In a real encoder (x264enc, etc.), this would:
        - Take raw video frames
        - Compress them using a codec
        - Output encoded frames

        Here we just transform the data field.
        """
        # Make buffer writable (copy if needed)
        buffer = buffer.make_writable()

        # Transform the data
        input_data = buffer.data
        encoded_data = {
            "type": "encoded_packet",
            "codec": self.codec,
            "frame_number": self.frame_count,
            "original": input_data,
            "encoded_payload": f"[{self.codec.upper()}-ENCODED: {input_data.get('payload', 'unknown')}]",
            "bitrate": "2000kbps",  # Simulated
            "compression_ratio": 0.3  # Simulated
        }

        buffer.data = encoded_data
        buffer.metadata[f"{self.name}_processed"] = True

        self.frame_count += 1

        logger.debug(f"  {self.name} - Encoded frame {self.frame_count}")

        return buffer
