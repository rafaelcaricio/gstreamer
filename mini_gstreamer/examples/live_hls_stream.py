#!/usr/bin/env python3
"""
Live HLS Streaming Example

This demonstrates a complete mini-GStreamer pipeline that:
1. Generates fake data (DataSource)
2. Encodes it (Encoder)
3. Segments it into HLS chunks (HLSSegmenter)
4. Uploads to S3 (S3Sink)

The key learning: Watch the call stack!
When DataSource calls gst_pad_push(), it creates a SYNCHRONOUS call chain:
  DataSource.push() ->
    Encoder.chain() ->
      Encoder.push() ->
        Segmenter.chain() ->
          Segmenter.push() ->
            S3Sink.chain() ->
            return to Segmenter
          return to Encoder
        return to DataSource

This is EXACTLY how GStreamer works!
"""

import sys
import time
import logging
from pathlib import Path

# Add parent directory to path so we can import mini-gstreamer
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mini_gstreamer.core import Pipeline, State, StateChangeReturn
from mini_gstreamer.elements import DataSource, Encoder, HLSSegmenter, S3Sink


def setup_logging():
    """Configure logging to show the call stack"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)-8s | %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/tmp/mini-gstreamer.log', mode='w')
        ]
    )

    # Set specific loggers
    logging.getLogger('core.pad').setLevel(logging.DEBUG)


def main():
    """Create and run the pipeline"""
    print("\n" + "="*80)
    print("MINI-GSTREAMER: Live HLS Streaming Pipeline")
    print("="*80)
    print("\nThis demonstrates how GStreamer's synchronous call chain works!")
    print("Watch the logs to see buffers flowing through the pipeline.\n")

    setup_logging()

    # Create pipeline
    # Like: pipeline = gst_pipeline_new("live-stream")
    pipeline = Pipeline("live-stream")

    # Create elements
    # Like GStreamer element factory:
    #   source = gst_element_factory_make("videotestsrc", "src")
    #   encoder = gst_element_factory_make("x264enc", "enc")
    #   etc.
    source = DataSource("datasource", data_rate=0.5, max_buffers=10)
    encoder = Encoder("encoder", codec="h264")
    segmenter = HLSSegmenter("segmenter", segment_duration=5.0)
    sink = S3Sink("s3sink", bucket="my-live-stream", prefix="live/", simulate=True)

    # Add elements to pipeline
    # Like: gst_bin_add_many(pipeline, source, encoder, segmenter, sink, NULL)
    pipeline.add(source, encoder, segmenter, sink)

    # Link elements
    # Like: gst_element_link_many(source, encoder, segmenter, sink, NULL)
    print("\n" + "-"*80)
    print("LINKING ELEMENTS")
    print("-"*80)
    source.link(encoder)
    encoder.link(segmenter)
    segmenter.link(sink)
    print()

    # Show pipeline structure
    print("-"*80)
    print("PIPELINE STRUCTURE")
    print("-"*80)
    print(f"  {source.name} (source)")
    print(f"    | src -> sink")
    print(f"  {encoder.name} (transform)")
    print(f"    | src -> sink")
    print(f"  {segmenter.name} (transform)")
    print(f"    | src -> sink")
    print(f"  {sink.name} (sink)")
    print()

    # Start the pipeline
    # Like: gst_element_set_state(pipeline, GST_STATE_PLAYING)
    print("-"*80)
    print("STARTING PIPELINE")
    print("-"*80)

    # State transitions: NULL -> READY -> PAUSED -> PLAYING
    # Must go through each state in order
    ret = pipeline.set_state(State.READY)
    if ret == StateChangeReturn.FAILURE:
        print("ERROR: Failed to transition to READY!")
        return 1

    ret = pipeline.set_state(State.PAUSED)
    if ret == StateChangeReturn.FAILURE:
        print("ERROR: Failed to transition to PAUSED!")
        return 1

    ret = pipeline.set_state(State.PLAYING)
    if ret == StateChangeReturn.FAILURE:
        print("ERROR: Failed to transition to PLAYING!")
        return 1

    print("\n" + "="*80)
    print("PIPELINE RUNNING - Watch the synchronous call chain!")
    print("="*80)
    print("\nKey things to observe:")
    print("1. When DataSource calls push(), it doesn't return until the buffer")
    print("   has flowed through the ENTIRE pipeline")
    print("2. Each element's chain() function is called SYNCHRONOUSLY")
    print("3. Return values bubble back up the stack")
    print("4. This is a DIRECT CALL STACK - no message passing!")
    print()

    try:
        # Let it run
        # In real GStreamer, you'd typically:
        #   bus = gst_pipeline_get_bus(pipeline)
        #   msg = gst_bus_timed_pop_filtered(bus, timeout, GST_MESSAGE_ERROR | GST_MESSAGE_EOS)
        #
        # Here we just sleep and let the source thread do its work
        while source.running:
            time.sleep(1)

        print("\n" + "="*80)
        print("STREAM COMPLETE")
        print("="*80)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    finally:
        # Stop the pipeline
        print("\n" + "-"*80)
        print("STOPPING PIPELINE")
        print("-"*80)
        pipeline.set_state(State.NULL)

        print("\nPipeline stopped.")
        print(f"\nSegments saved to: /tmp/mini-gstreamer-segments/")
        print(f"Full log saved to: /tmp/mini-gstreamer.log\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
