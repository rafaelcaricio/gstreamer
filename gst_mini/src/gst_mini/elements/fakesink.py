from ..core.element import GstElement
from ..core.pad import GstFlowReturn
from ..core.buffer import GstBuffer


class FakeSink(GstElement):
    def __init__(self, name):
        super().__init__(name)
        self.buffer_count = 0

        self.sink_pad = self.create_sink_pad("sink")
        self.sink_pad.set_chain_function(self._chain)

    def on_ready(self):
        self.buffer_count = 0

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        self.buffer_count += 1
        print(f"[{self.pipeline.clock.get_time():.3f}s] {self.name}: Received {repr(buffer)}")
        return GstFlowReturn.OK
