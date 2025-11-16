#!/usr/bin/env python3
"""
Simple example showing buffer synchronization.

Manually creates buffers and pushes them through a sink,
demonstrating the clock wait mechanism.

Pipeline:
    Manual buffers → S3Sink (with sync)
"""

from gst_mini import GstPipeline, GstState, GstBuffer, GstSegment, S3Sink


def main():
    print("=" * 80)
    print("Simple Synchronization Example")
    print("=" * 80)
    print()
    print("Manually pushing 5 buffers with increasing timestamps")
    print("Watch for clock waits demonstrating synchronization")
    print()
    print("=" * 80)
    print()

    # Create pipeline
    pipeline = GstPipeline("simple-pipeline")

    # Create sink
    sink = S3Sink("sink", bucket="test-bucket", sync=True)

    # Add to pipeline
    pipeline.add(sink)

    # Set up segment
    sink.segment = GstSegment(start=0.0, rate=1.0, base=0.0)

    # Set to PLAYING
    pipeline.set_state(GstState.PLAYING)

    print(f"[{pipeline.clock.get_time():.3f}s] Pushing buffers manually...\n")

    # Create and push buffers with increasing timestamps
    for i in range(5):
        pts = i * 2.0  # 2 seconds apart
        buffer = GstBuffer(
            pts=pts,
            duration=2.0,
            data={'segment_num': i, 'buffers': [], 'duration': 2.0}
        )

        print(f"[{pipeline.clock.get_time():.3f}s] Pushing buffer {i} with PTS={pts}s")
        sink.sink_pad._chain(buffer)
        print()

    # Cleanup
    pipeline.set_state(GstState.NULL)

    print()
    print("=" * 80)
    print("Notice:")
    print("  • Each buffer waited until its timestamp matched clock time")
    print("  • running_time = PTS (since segment.start=0, segment.base=0)")
    print("  • clock_time = running_time + base_time")
    print("  • Synchronization formula: wait until clock >= clock_time")
    print("=" * 80)


if __name__ == '__main__':
    main()
