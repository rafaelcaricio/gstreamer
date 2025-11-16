from gst_mini import GstPipeline, LiveSource, VideoEnc, FakeSink
from gst_mini import GstElement, GstBuffer, GstFlowReturn, BufferFlags
from typing import Optional


class Muxer(GstElement):
    def __init__(self, name: str, target_duration: float = 2.0):
        super().__init__(name)
        self.target_duration = target_duration

        self._buffer: Optional[GstBuffer] = None

        self.sink_pad = self.create_sink_pad()
        self.sink_pad.set_chain_function(self._chain)
        self.src_pad = self.create_src_pad()

    def on_ready(self):
        self.buffer = None

    def _chain(self, buffer: GstBuffer) -> GstFlowReturn:
        # Waits for iframe buffers (considering video content)
        if not buffer.has_flag(BufferFlags.DELTA_UNIT):
            self.log(f"New segment starting at PTS={buffer.pts:.3f}s")
            # this is a keyframe we could pontentially push down now
            if self._buffer is not None:
                # push previous segment
                self.log(f"Pushing segment with duration {self._buffer.duration:.3f}s")
                if self.src_pad.push(self._buffer) != GstFlowReturn.OK:
                    self.log("Failed to push segment")

            self._buffer = GstBuffer(
                pts=buffer.pts,
                duration=buffer.duration,
                data={
                    'frames': [buffer.data],
                }
            )
        else:
            # accumulate buffer into current segment
            if self._buffer is not None:
                self._buffer.duration += buffer.duration
                self._buffer.data['frames'].append(buffer.data)
            else:
                # no keyframe received yet, drop buffer
                pass

        return GstFlowReturn.OK


def main():
    pipeline = GstPipeline("test-pipeline")

    source = LiveSource("camera", fps=30)
    video_enc = VideoEnc("videoenc", gop_size=60)
    muxer = Muxer("muxer")
    sink = FakeSink("fakesink")

    pipeline.add(source, video_enc, muxer, sink)
    pipeline.link(source, video_enc)
    pipeline.link(video_enc, muxer)
    pipeline.link(muxer, sink)

    pipeline.run(duration=8)

    print("\n" + "="*60)
    print(f"Generated: {source.frame_count} frames")
    print(f"Captured: {sink.buffer_count} buffers")
    print("="*60)

if __name__ == '__main__':
    main()
