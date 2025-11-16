#!/usr/bin/env python3
"""
Full HLS pipeline example with live source, queue, segmenter, and S3 sink.

This demonstrates the complete GStreamer-like pipeline with:
- LiveSource generating frames at 30fps
- Queue decoupling threads
- HLSSegmenter grouping frames into 6s segments
- S3Sink uploading segments with synchronization

Pipeline:
    LiveSource (30fps) → Queue → HLSSegmenter → S3Sink
       Thread A           ↓        Thread B
                       mutex + queue
"""

from gst_mini import GstPipeline, GstState, LiveSource, Queue, HLSSegmenter, S3Sink


def main():
    print("=" * 80)
    print("Full HLS Pipeline Example")
    print("=" * 80)
    print()
    print("Pipeline: LiveSource → Queue → HLSSegmenter → S3Sink")
    print("- LiveSource generates 30 frames/sec")
    print("- Queue decouples threads (max 10 buffers, leaky upstream)")
    print("- HLSSegmenter creates 6-second segments")
    print("- S3Sink uploads with synchronization")
    print()
    print("Watch for:")
    print("  • Frame generation at steady rate (Thread A)")
    print("  • Queue filling/emptying")
    print("  • Segment creation every 6 seconds")
    print("  • Clock waits before upload (Thread B)")
    print("  • No blocking of frame generation!")
    print()
    print("=" * 80)
    print()

    # Create pipeline
    pipeline = GstPipeline("hls-pipeline")

    # Create elements
    source = LiveSource("camera", fps=30)
    queue = Queue("queue", max_size=10, leaky="upstream")
    segmenter = HLSSegmenter("segmenter", target_duration=6.0)
    sink = S3Sink("s3sink", bucket="live-streams", sync=True)

    # Add to pipeline
    pipeline.add(source, queue, segmenter, sink)

    # Link elements
    pipeline.link(source, queue)
    pipeline.link(queue, segmenter)
    pipeline.link(segmenter, sink)

    # Run for 20 seconds
    pipeline.run(duration=20.0)

    # Print statistics
    print()
    print("=" * 80)
    print("Statistics:")
    print("-" * 80)

    source_stats = source.get_stats()
    print(f"LiveSource: {source_stats['frames_generated']} frames generated, "
          f"{source_stats['frames_dropped']} dropped")

    queue_stats = queue.get_stats()
    print(f"Queue: {queue_stats['buffers_in']} in, {queue_stats['buffers_out']} out, "
          f"{queue_stats['buffers_dropped']} dropped")

    print(f"S3Sink: {sink.segment_count} segments uploaded")
    print("=" * 80)


if __name__ == '__main__':
    main()
