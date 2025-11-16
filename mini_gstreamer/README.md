# Mini-GStreamer: Educational Implementation

A simplified, educational implementation of GStreamer's pipeline architecture that demonstrates the core concepts through a live HLS streaming example.

## Overview

This project implements the essential mechanics of GStreamer:
- **Pipeline**: Top-level container managing state
- **Elements**: Processing units with pads
- **Pads**: Connection points between elements
- **Synchronous Call Chain**: The key insight - buffers flow through **direct function calls**!

## The Key Insight: Synchronous Call Stack

When you call `gst_pad_push()` in GStreamer, it creates a **synchronous call chain**:

```
DataSource.push()
  → gst_pad_push_data()
    → gst_pad_chain_data_unchecked(peer_pad)
      → chainfunc = GST_PAD_CHAINFUNC(peer_pad)
      → Encoder.chain()               // <-- Direct function call!
        → process data
        → gst_pad_push()
          → Segmenter.chain()         // <-- Another direct call!
            → buffer data
            → gst_pad_push()
              → S3Sink.chain()        // <-- Final call!
                → upload to S3
                → return FLOW_OK
              ← return to Segmenter
            ← return to Encoder
          ← return to DataSource
```

**This is NOT message passing!** It's a direct call stack, all synchronous.

## Project Structure

```
mini-gstreamer/
├── core/               # Base abstractions
│   ├── buffer.py       # Buffer data container
│   ├── pad.py          # Pads with chain functions ⭐ KEY FILE
│   ├── element.py      # Element base class
│   └── pipeline.py     # Pipeline container
├── elements/           # Concrete elements
│   ├── datasource.py   # Generates fake data in thread
│   ├── encoder.py      # Transforms data (demonstrates chain)
│   ├── segmenter.py    # Creates HLS segments
│   └── s3sink.py       # Uploads to S3
└── examples/
    └── live_hls_stream.py  # Complete working example
```

## Running the Example

```bash
cd mini-gstreamer
python3 examples/live_hls_stream.py
```

This creates a pipeline:
```
DataSource → Encoder → HLSSegmenter → S3Sink
```

Watch the logs to see the **synchronous call chain** in action!

## Key Code to Study

### 1. Pad.push() - Starts the chain
File: `core/pad.py:141`

```python
def push(self, buffer: Buffer) -> FlowReturn:
    """THE KEY: Direct synchronous call to peer's chain function"""
    # Find peer pad
    if self.peer is None:
        return FlowReturn.NOT_LINKED

    # DIRECT CALL to peer's chain function
    return self._chain_on_peer(buffer)
```

### 2. Pad._chain_on_peer() - Calls the function
File: `core/pad.py:166`

```python
def _chain_on_peer(self, buffer: Buffer) -> FlowReturn:
    # Get the chain function pointer
    chain_func = peer._chain_function

    # DIRECT FUNCTION CALL - creates the call stack!
    ret = chain_func(peer, buffer)
    return ret
```

### 3. Element.set_chain_function() - Registers handler
File: `core/pad.py:104`

Elements register their chain function:
```python
self.sink_pad.set_chain_function(self._chain)
```

### 4. Encoder._chain() - Process and push
File: `elements/encoder.py:46`

```python
def _chain(self, pad: Pad, buffer: Buffer) -> FlowReturn:
    # Receive buffer
    encoded = self._encode(buffer)

    # Push downstream (continues the chain!)
    return self.src_pad.push(encoded)
```

## State Transitions

Like GStreamer, elements transition through states:

```
NULL → READY → PAUSED → PLAYING
  ↓       ↓       ↓        ↓
  -    Allocate  Activate  Start
       Resources  Pads   Streaming
```

- **NULL → READY**: Allocate resources
- **READY → PAUSED**: Activate pads (source pads first!)
- **PAUSED → PLAYING**: Start streaming thread (sources)
- **PLAYING → PAUSED**: Stop thread
- **PAUSED → READY**: Deactivate pads
- **READY → NULL**: Free resources

## Pad Activation

During READY → PAUSED transition (`element.py:205`):
1. Source pads activated first
2. Then sink pads
3. Each pad set to PUSH mode

This mirrors GStreamer's activation sequence.

## Threading Model

- **Source elements** (DataSource) run in their own thread
- They call `pad.push()` which creates synchronous call chain
- **Stream lock** on each pad ensures only one buffer at a time
- Result: One thread executes the entire chain!

## Comparison to Real GStreamer

| Mini-GStreamer | Real GStreamer | Location in Real GStreamer |
|----------------|----------------|---------------------------|
| `Pad.push()` | `gst_pad_push()` | `gstpad.c:4963` |
| `Pad._chain_on_peer()` | `gst_pad_chain_data_unchecked()` | `gstpad.c:4497` |
| `chain_func(pad, buffer)` | `chainfunc(pad, parent, buffer)` | `gstpad.c:4560` |
| `Element._activate_pads()` | `gst_element_pads_activate()` | `gstelement.c:3212` |
| `DataSource._source_loop()` | `gst_base_src_loop()` | `gstbasesrc.c:2881` |

## What We Learned

1. **Buffer flow is synchronous** - direct function calls, not messages
2. **Chain functions** are the heart of processing
3. **Pads** hold function pointers that get called
4. **State transitions** follow a strict order
5. **Pad activation** happens before streaming starts
6. **Source elements** run in threads and start the call chain
7. **Return values** (FlowReturn) bubble up the stack
8. **Stream locks** ensure thread safety

## Output

Segments are saved to `/tmp/mini-gstreamer-segments/` as JSON files.
Full execution log saved to `/tmp/mini-gstreamer.log`.

## Next Steps

To understand GStreamer even better:
1. Add event system (STREAM_START, CAPS, SEGMENT, EOS)
2. Implement caps negotiation
3. Add probe mechanism for debugging
4. Create pull-mode support
5. Implement GstBus for messaging
6. Add query system

## References

- Real GStreamer source: `/home/user/gstreamer/subprojects/gstreamer/`
- Key files studied:
  - `gst/gstpad.c` - Pad implementation
  - `gst/gstelement.c` - Element base class
  - `gst/gstpipeline.c` - Pipeline
  - `libs/gst/base/gstbasesrc.c` - Source base class
  - `libs/gst/base/gstbasetransform.c` - Transform base class

---

Built to understand GStreamer's elegant architecture! 🎬
