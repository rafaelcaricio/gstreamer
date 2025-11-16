# GstMini Examples

This directory contains example scripts demonstrating various GstMini concepts.

## Running Examples

All examples can be run using `uv`:

```bash
# Quick test (8 seconds)
uv run examples/quick_test.py

# Simple synchronization demonstration
uv run examples/simple_sync.py

# Full pipeline with queue (recommended - 20 seconds)
uv run examples/full_pipeline.py

# Pipeline without queue (shows blocking problem - 20 seconds)
uv run examples/without_queue.py
```

## Example Descriptions

### quick_test.py
Quick 8-second test of the complete pipeline with 3-second segments.
Good for verifying everything works.

### simple_sync.py
Manually creates and pushes 5 buffers to demonstrate the synchronization formula.
Educational example showing how clock waits work.

### full_pipeline.py (Recommended)
Complete HLS pipeline demonstrating smooth operation with a queue:
- LiveSource generating 30fps
- Queue decoupling threads
- HLSSegmenter grouping frames into 6-second segments
- S3Sink uploading with synchronization

Watch for steady frame generation despite sink waits!

### without_queue.py
Demonstrates the blocking problem when no queue is used.
Shows why queues are essential for live sources.

## Learning Path

1. Run `simple_sync.py` to understand basic synchronization
2. Run `full_pipeline.py` to see the complete working system
3. Run `without_queue.py` to understand why queues matter
4. Experiment by modifying parameters (fps, segment duration, etc.)
