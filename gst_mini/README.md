# GstMini - Simplified GStreamer Learning Framework

A simplified implementation of GStreamer's core concepts for educational purposes. This framework demonstrates buffer synchronization, timing, and thread management in multimedia pipelines.

## Overview

GstMini captures the essential mechanics of GStreamer without handling real multimedia content:

- **Pipeline**: Container managing elements and clock
- **Elements**: Processing units (Source, Queue, Segmenter, Sink)
- **Pads**: Connection points with chain functions
- **Buffers**: Data units carrying timestamps
- **Synchronization**: Clock-based timing at sinks
- **Threading**: Queue-based decoupling

## Architecture

```
LiveSource (30fps) → Queue → HLSSegmenter → S3Sink
   Thread A           ↓        Thread B
                   mutex
                 + buffer queue
```

## Core Concepts Demonstrated

### 1. Buffer Flow via Chain Calls

**Code**: `core/pad.py:push()` → `core/pad.py:_chain()`

- Buffers flow synchronously through chain function calls
- Each element's chain function processes and forwards buffers
- Chain calls are **blocking** - upstream waits for downstream

**GStreamer Reference**: `gstpad.c:4497-4586`

### 2. Timestamps and Time Domains

**Code**: `core/buffer.py:GstBuffer`

Every buffer carries:
- `pts`: Presentation timestamp (when to display)
- `duration`: Buffer duration
- `data`: Payload

**GStreamer Reference**: `gstbuffer.h:80-133`

### 3. Segment Conversion

**Code**: `core/segment.py:to_running_time()`

Converts stream time to running time:
```python
running_time = (pts - segment.start) / segment.rate + segment.base
```

**GStreamer Reference**: `gstsegment.c:822-867`

### 4. Queue Thread Decoupling

**Code**: `elements/queue.py`

**Critical for live pipelines!**

Two threads:
1. **Chain function** (upstream thread): Enqueues buffers
2. **Loop function** (downstream thread): Dequeues and pushes

This prevents live sources from blocking on sync waits.

**GStreamer Reference**: `gstqueue.c:1271-1639`

### 5. Synchronization at Sink

**Code**: `elements/s3sink.py:_chain()`

The synchronization formula:
```python
running_time = segment.to_running_time(pts)
clock_time = running_time + base_time
clock.wait_until(clock_time)  # BLOCKS here!
```

**GStreamer Reference**:
- `gstbasesink.c:2665-2828` (do_sync)
- `gstbasesink.c:2333-2404` (wait_clock)

## Directory Structure

```
gst_mini/
├── core/
│   ├── buffer.py       # GstBuffer with timestamps
│   ├── segment.py      # Time domain conversion
│   ├── pad.py          # Chain call mechanism
│   ├── element.py      # Base element class
│   ├── pipeline.py     # Pipeline container
│   └── clock.py        # Timing and synchronization
├── elements/
│   ├── livesource.py   # Generates frames at 30fps
│   ├── queue.py        # Thread decoupling
│   ├── hlssegmenter.py # Groups frames into segments
│   └── s3sink.py       # Uploads with synchronization
└── examples/
    ├── full_pipeline.py    # Complete HLS pipeline
    ├── without_queue.py    # Shows blocking problem
    └── simple_sync.py      # Basic synchronization
```

## Running Examples

### Full Pipeline (Recommended Start)

```bash
cd gst_mini
python3 examples/full_pipeline.py
```

**What to observe**:
- LiveSource generates frames at steady 30fps
- Queue fills and empties
- Segments created every 6 seconds
- S3Sink waits on clock before "uploading"
- Frame generation never blocks!

### Without Queue (Demonstrates Problem)

```bash
python3 examples/without_queue.py
```

**What to observe**:
- Frame generation becomes irregular
- LiveSource blocks during sync waits
- **This shows WHY queues are essential!**

### Simple Synchronization

```bash
python3 examples/simple_sync.py
```

**What to observe**:
- Manual buffer pushing
- Clock wait mechanism
- Timing formula in action

## Learning Path

### Phase 1: Understanding Data Flow

1. Read `core/buffer.py` - See how timestamps are stored
2. Read `core/pad.py` - Understand chain calls
3. Run `simple_sync.py` - See synchronization in action

**Key Insight**: Chain calls are synchronous and blocking.

### Phase 2: Understanding Timing

1. Read `core/segment.py` - Time domain conversion
2. Read `core/clock.py` - Clock wait mechanism
3. Read `elements/s3sink.py:_chain()` - See synchronization formula

**Key Insight**: Sync happens at sinks, not during chain calls.

### Phase 3: Understanding Threading

1. Read `elements/livesource.py` - Live frame generation
2. Run `without_queue.py` - See the blocking problem
3. Read `elements/queue.py` - Thread decoupling solution
4. Run `full_pipeline.py` - See smooth operation

**Key Insight**: Queues separate fast producers from slow consumers.

### Phase 4: Understanding Buffering

1. Read `elements/hlssegmenter.py` - Accumulation strategy
2. Modify `target_duration` in examples
3. Modify `max_size` and `leaky` mode in queue

**Key Insight**: Buffering enables batching and handles rate mismatches.

## Experiments to Try

### 1. Disable Queue

In `full_pipeline.py`, remove the queue and link source directly to segmenter:
```python
# pipeline.link(source, queue)
# pipeline.link(queue, segmenter)
pipeline.link(source, segmenter)  # Direct link
```

**Expected**: Irregular frame generation, blocking.

### 2. Disable Synchronization

Set `sync=False` in S3Sink:
```python
sink = S3Sink("s3sink", bucket="live-streams", sync=False)
```

**Expected**: Segments "upload" immediately, no clock waits.

### 3. Change Queue Size

Try different queue sizes:
```python
queue = Queue("queue", max_size=3, leaky="upstream")   # Small queue
queue = Queue("queue", max_size=100, leaky=None)       # Large queue, blocking
```

**Expected**:
- Small queue with leaky: drops frames when full
- Large queue without leaky: never drops, but high latency

### 4. Change Leaky Mode

```python
queue = Queue("queue", max_size=10, leaky="downstream")  # Drop old buffers
```

**Expected**: Maintains low latency by dropping old data.

### 5. Vary FPS and Segment Duration

```python
source = LiveSource("camera", fps=60)  # Higher frame rate
segmenter = HLSSegmenter("segmenter", target_duration=2.0)  # Shorter segments
```

**Expected**: More frequent segment creation.

## Code Mapping to Real GStreamer

| GstMini Component | Real GStreamer | File:Line |
|-------------------|----------------|-----------|
| `GstBuffer.pts` | `GST_BUFFER_PTS` | `gstbuffer.h:89` |
| `GstSegment.to_running_time()` | `gst_segment_to_running_time()` | `gstsegment.c:822` |
| `GstPad.push()` | `gst_pad_push()` | `gstpad.c:4795` |
| `GstPad._chain()` | `gst_pad_chain_data_unchecked()` | `gstpad.c:4497` |
| `Queue._chain()` | `gst_queue_chain_buffer_or_list()` | `gstqueue.c:1271` |
| `Queue._loop()` | `gst_queue_loop()` | `gstqueue.c:1590` |
| `S3Sink._chain()` | `gst_base_sink_do_sync()` | `gstbasesink.c:2665` |
| `GstClock.wait_until()` | `gst_base_sink_wait_clock()` | `gstbasesink.c:2333` |

## Key Takeaways

1. **Buffers carry timestamps** - Set once by source, preserved through pipeline
2. **Segments define time domains** - Enable seeking, rate changes
3. **Chain calls are synchronous** - Blocking data flow
4. **Synchronization happens at sinks** - Via clock waits
5. **Queues decouple threads** - Essential for live sources
6. **The sync formula**: `clock_time = running_time + base_time`
7. **Thread safety**: Mutexes protect queue, pad stream locks serialize data

## Differences from Real GStreamer

Simplified for learning:

- No caps negotiation
- No events (except implicit segment)
- No queries
- No buffer pools or memory management
- No state change ordering
- No preroll mechanism
- Single clock (no clock providers/selection)
- No activation modes (push/pull)
- No scheduling/chain optimization
- Simplified error handling

These simplifications let you focus on the **core synchronization concepts** without getting lost in GStreamer's full complexity.

## Next Steps

After understanding GstMini:

1. **Read the research document**: `BUFFER_SYNC_RESEARCH.md` in parent directory
2. **Explore real GStreamer code** using the file:line references
3. **Build a real pipeline** with GStreamer applying these concepts
4. **Extend GstMini** - Add features like:
   - Multiple sinks (audio + video sync)
   - Seeking support
   - QoS events
   - Buffer pools
   - More element types

## Questions to Explore

1. What happens if `base_time` is set differently for different sinks?
2. How does the queue decide when to drop buffers?
3. Why does running time reset on a flush seek?
4. How would you implement rate changes (slow motion)?
5. What happens if clock time goes backwards?

Happy learning!
