
from ..core.element import GstElement
from ..core.buffer import GstBuffer, BufferFlags
from ..core.pad import GstFlowReturn


class VideoEnc(GstElement):

    def __init__(self, name: str, gop_size: int = 30):
        """
        Create a video encoder element.

        Args:
            name: Element name
            gop_size: Group of Pictures size
        """
        super().__init__(name)
        # properties
        self.gop_size = gop_size

        # state
        self.processed_frames = 0

        self.sink_pad = self.create_sink_pad("sink")
        self.sink_pad.set_chain_function(self._chain)
        self.src_pad = self.create_src_pad("src")

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        # A fake encoding by counting the number of buffers and set the flags
        if buffer.has_flag(BufferFlags.EOS):
            self.log("Received EOS")
            return GstFlowReturn.EOS

        if self.processed_frames % self.gop_size == 0:
            buffer.unset_flag(BufferFlags.DELTA_UNIT)
            self.log(f"Encoded IDR frame #{self.processed_frames}")
        else:
            buffer.set_flag(BufferFlags.DELTA_UNIT)
        self.processed_frames += 1

        return self.src_pad.push(buffer)
