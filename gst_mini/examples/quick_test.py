#!/usr/bin/env python3
"""Quick test of the full pipeline."""

from gst_mini import GstPipeline, LiveSource, Queue, HLSSegmenter, S3Sink

def main():
    print("Quick Pipeline Test (8 seconds)")
    print("="*60)

    pipeline = GstPipeline("test-pipeline")

    source = LiveSource("camera", fps=30)
    queue = Queue("queue", max_size=10, leaky="upstream")
    segmenter = HLSSegmenter("segmenter", target_duration=2.0)  # Shorter segments
    sink = S3Sink("s3sink", bucket="test", sync=True)

    pipeline.add(source, queue, segmenter, sink)
    pipeline.link(source, queue)
    pipeline.link(queue, segmenter)
    pipeline.link(segmenter, sink)

    pipeline.run(duration=8.0)

    print("\n" + "="*60)
    print(f"Generated: {source.frame_count} frames")
    print(f"Uploaded: {sink.segment_count} segments")
    print("="*60)

if __name__ == '__main__':
    main()
