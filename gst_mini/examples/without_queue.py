#!/usr/bin/env python3
"""
Example WITHOUT queue - demonstrates blocking problem.

This shows why queues are essential in live pipelines:
- LiveSource tries to push frames directly to segmenter
- Segmenter pushes to S3Sink
- S3Sink waits on clock (synchronization)
- LiveSource BLOCKS during clock wait!
- Frame generation becomes irregular

Pipeline:
    LiveSource (30fps) → HLSSegmenter → S3Sink
           (all in same thread - BLOCKS!)

Compare this to the full_pipeline.py example with a queue.
"""

import sys
import os

# Add parent directory to path to import gst_mini package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from gst_mini import GstPipeline, GstState, LiveSource, HLSSegmenter, S3Sink


def main():
    print("=" * 80)
    print("Pipeline WITHOUT Queue - Demonstrates Blocking Problem")
    print("=" * 80)
    print()
    print("Pipeline: LiveSource → HLSSegmenter → S3Sink")
    print("  (NO QUEUE - everything in same thread)")
    print()
    print("Watch for:")
    print("  • Irregular frame generation")
    print("  • LiveSource blocks during S3 upload")
    print("  • Frame timing becomes inconsistent")
    print()
    print("This demonstrates WHY queues are critical for live sources!")
    print()
    print("=" * 80)
    print()

    # Create pipeline
    pipeline = GstPipeline("no-queue-pipeline")

    # Create elements (NO QUEUE!)
    source = LiveSource("camera", fps=30)
    segmenter = HLSSegmenter("segmenter", target_duration=6.0)
    sink = S3Sink("s3sink", bucket="live-streams", sync=True)

    # Add to pipeline
    pipeline.add(source, segmenter, sink)

    # Link elements directly (no queue in between)
    pipeline.link(source, segmenter)
    pipeline.link(segmenter, sink)

    # Run for 20 seconds
    pipeline.run(duration=20.0)

    # Print statistics
    print()
    print("=" * 80)
    print("Statistics:")
    print("-" * 80)

    source_stats = source.get_stats()
    print(f"LiveSource: {source_stats['frames_generated']} frames generated")
    print(f"            {source_stats['frames_dropped']} frames dropped")
    print()
    print("Note: With a queue, frame generation would be smooth!")
    print("      See full_pipeline.py for comparison.")
    print("=" * 80)


if __name__ == '__main__':
    main()
