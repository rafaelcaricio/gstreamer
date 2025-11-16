# GStreamer Buffer Synchronization Research

## Overview

This document explains how time and synchronization of buffers work in GStreamer, particularly focusing on how buffers are passed through chain calls, how synchronization is maintained, and how queues affect timing in live pipelines.

## 1. Buffer Chain Calls: How Pads Pass Buffers

### The Chain Call Mechanism

Buffers flow through a GStreamer pipeline via **chain functions**. When an element pushes a buffer, it calls `gst_pad_push()`, which ultimately invokes the downstream element's chain function.

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/gst/gstpad.c:4795-4839`**

```c
static GstFlowReturn
gst_pad_push_data (GstPad * pad, GstPadProbeType type, void *data)
{
  GstPad *peer;
  GstFlowReturn ret;

  // Check for flushing, EOS, wrong mode
  GST_OBJECT_LOCK (pad);
  if (G_UNLIKELY (GST_PAD_IS_FLUSHING (pad)))
    goto flushing;

  // Ensure STREAM_START and SEGMENT events were sent before data
  if (!find_event_by_type (pad, GST_EVENT_STREAM_START, 0)) {
    g_warning ("Got data flow before stream-start event");
  }
  if (!find_event_by_type (pad, GST_EVENT_SEGMENT, 0)) {
    g_warning ("Got data flow before segment event");
  }

  // Execute pad probes (can block or modify data)
  PROBE_HANDLE (pad, type | GST_PAD_PROBE_TYPE_BLOCK, data, ...);
  PROBE_HANDLE (pad, type, data, ...);

  // Get peer pad and push to it
  peer = gst_pad_get_peer (pad);
  ret = gst_pad_chain_data_unchecked (peer, type, data);

  return ret;
}
```

The actual chain function invocation happens in `gst_pad_chain_data_unchecked()`:

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/gst/gstpad.c:4497-4586`**

```c
static inline GstFlowReturn
gst_pad_chain_data_unchecked (GstPad * pad, GstPadProbeType type, void *data)
{
  GstPadChainFunction chainfunc;
  GstFlowReturn ret;

  GST_PAD_STREAM_LOCK (pad);  // Serialize data flow

  // Check state
  if (G_UNLIKELY (GST_PAD_IS_FLUSHING (pad)))
    goto flushing;

  // Execute probes
  PROBE_HANDLE (pad, type | GST_PAD_PROBE_TYPE_BLOCK, data, ...);

  // Get the chain function and call it
  if (G_LIKELY (type & GST_PAD_PROBE_TYPE_BUFFER)) {
    chainfunc = GST_PAD_CHAINFUNC (pad);

    GST_CAT_DEBUG_OBJECT (GST_CAT_SCHEDULING, pad,
        "calling chainfunction &%s with buffer",
        GST_DEBUG_FUNCPTR_NAME (chainfunc));

    ret = chainfunc (pad, parent, GST_BUFFER_CAST (data));
  }

  GST_PAD_STREAM_UNLOCK (pad);
  return ret;
}
```

**Key Points:**
- Chain calls are **synchronous** - the upstream element waits until the downstream chain function returns
- The `GST_PAD_STREAM_LOCK` ensures only one buffer flows through a pad at a time
- Pad probes can intercept buffers for monitoring or modification
- SEGMENT events must be sent before buffers to establish the time domain

## 2. Buffer Timestamps: The Foundation of Synchronization

Every buffer carries timing information in its structure:

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/gst/gstbuffer.h:80-133`**

```c
// Presentation timestamp - when to display/present the buffer
#define GST_BUFFER_PTS(buf)      (GST_BUFFER_CAST(buf)->pts)

// Decoding timestamp - when to decode the buffer
#define GST_BUFFER_DTS(buf)      (GST_BUFFER_CAST(buf)->dts)

// Duration of the buffer
#define GST_BUFFER_DURATION(buf) (GST_BUFFER_CAST(buf)->duration)

// Offset in the source (e.g., byte position)
#define GST_BUFFER_OFFSET(buf)   (GST_BUFFER_CAST(buf)->offset)
```

**Timestamp Types:**
- **PTS (Presentation Time Stamp)**: When the buffer should be presented to the user
- **DTS (Decoding Time Stamp)**: When the buffer should be decoded (relevant for encoded streams with B-frames)
- **Duration**: How long the buffer represents in time

These timestamps are set by the source element and flow downstream with the buffer. They represent time in the **stream's time domain**, not wall-clock time.

## 3. Segment Events: Converting Stream Time to Running Time

Before synchronization can occur, stream timestamps must be converted to **running time**. This conversion is defined by SEGMENT events.

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/gst/gstsegment.c:822-867`**

```c
/**
 * gst_segment_to_running_time:
 * @segment: a #GstSegment structure.
 * @format: the format of the segment.
 * @position: the position in the segment
 *
 * Translate @position to the total running time using the currently configured
 * segment. Position is a value between @segment start and stop time.
 *
 * This function is typically used by elements that need to synchronize to the
 * global clock in a pipeline. The running time is a constantly increasing value
 * starting from 0. When gst_segment_init() is called, this value will reset to 0.
 */
guint64
gst_segment_to_running_time (const GstSegment * segment, GstFormat format,
    guint64 position)
{
  // Check position is within segment boundaries
  if (G_UNLIKELY (position < segment->start))
    return -1;
  if (G_UNLIKELY (segment->stop != -1 && position > segment->stop))
    return -1;

  // Convert to running time accounting for:
  // - segment.start (trim from beginning)
  // - segment.rate (playback rate)
  // - segment.base (accumulated running time from previous segments)

  return result;
}
```

**The Segment Conversion Process:**

Segments allow for:
- **Seeking**: Start playback from a non-zero position
- **Rate changes**: Play faster/slower than 1.0x
- **Accumulation**: Track total running time across seeks

Example: If a segment has `start=5s, rate=1.0, base=0`, then:
- Buffer with PTS=5s → running_time = 0s
- Buffer with PTS=6s → running_time = 1s
- Buffer with PTS=7s → running_time = 2s

## 4. Queue Element: Thread Decoupling

Queues are critical for pipeline performance and live operation. They decouple upstream and downstream threads.

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/plugins/elements/gstqueue.c:1271-1376`**

### Queue Chain Function (Upstream Thread)

```c
static GstFlowReturn
gst_queue_chain_buffer_or_list (GstPad * pad, GstObject * parent,
    GstMiniObject * obj, gboolean is_list)
{
  GstQueue *queue = GST_QUEUE_CAST (parent);

  // Lock the queue for thread-safety
  GST_QUEUE_MUTEX_LOCK_CHECK (queue, out_flushing);

  // Refuse data if EOS was received
  if (queue->eos)
    goto out_eos;

  // Wait if queue is full according to configured limits
  while (gst_queue_is_filled (queue)) {
    switch (queue->leaky) {
      case GST_QUEUE_LEAK_UPSTREAM:
        // Drop this incoming buffer
        queue->tail_needs_discont = TRUE;
        goto out_unref;

      case GST_QUEUE_LEAK_DOWNSTREAM:
        // Drop old buffers from the queue
        gst_queue_leak_downstream (queue);
        break;

      case GST_QUEUE_NO_LEAK:
        // Block until space is available
        while (gst_queue_is_filled (queue)) {
          GST_QUEUE_WAIT_DEL_CHECK (queue, out_flushing);
        }
        break;
    }
  }

  // Mark buffer with DISCONT flag if we dropped buffers
  if (queue->tail_needs_discont) {
    GstBuffer *buffer = GST_BUFFER_CAST (obj);
    buffer = gst_buffer_make_writable (buffer);
    GST_BUFFER_FLAG_SET (buffer, GST_BUFFER_FLAG_DISCONT);
    queue->tail_needs_discont = FALSE;
  }

  // Enqueue the buffer
  gst_queue_locked_enqueue_buffer (queue, obj);
  GST_QUEUE_MUTEX_UNLOCK_NOTIFY_LEVELS (queue, prev_level);

  return GST_FLOW_OK;
}
```

### Queue Loop Function (Downstream Thread)

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/plugins/elements/gstqueue.c:1590-1639`**

```c
static void
gst_queue_loop (GstPad * pad)
{
  GstQueue *queue = (GstQueue *) GST_PAD_PARENT (pad);
  GstFlowReturn ret;

  GST_QUEUE_MUTEX_LOCK_CHECK (queue, out_flushing);

  // Wait while queue is empty
  while (gst_queue_is_empty (queue)) {
    GST_CAT_DEBUG_OBJECT (queue_dataflow, queue, "queue is empty");

    if (!queue->silent) {
      g_signal_emit (queue, gst_queue_signals[SIGNAL_UNDERRUN], 0);
    }

    // Block until data arrives
    while (gst_queue_is_empty (queue)) {
      GST_QUEUE_WAIT_ADD_CHECK (queue, out_flushing);
    }
  }

  // Push one buffer downstream
  ret = gst_queue_push_one (queue);
  queue->srcresult = ret;

  if (ret != GST_FLOW_OK)
    goto out_flushing;

  GST_QUEUE_MUTEX_UNLOCK_NOTIFY_LEVELS (queue, prev_level);
}
```

**Key Points about Queues:**
- **Two threads**: Chain function runs in upstream thread, loop function runs in downstream thread
- **Buffering**: Can hold buffers based on time, bytes, or buffer count limits
- **Leaky modes**: Can drop buffers (upstream or downstream) to prevent blocking
- **No timing modification**: Queues pass timestamps unchanged
- **DISCONT marking**: Marks discontinuities when buffers are dropped

## 5. BaseSink Synchronization: The Heart of Timing

BaseSink is where actual synchronization to the clock happens. This is where buffers wait until their presentation time.

### Getting Sync Times

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/libs/gst/base/gstbasesink.c:2147-2258`**

```c
// Extract buffer timestamps
GstBuffer *buffer = GST_BUFFER_CAST (obj);

// Get times from the buffer (usually PTS and PTS+duration)
if (bclass->get_times)
  bclass->get_times (basesink, buffer, &start, &stop);

// Clip to segment boundaries
if (!gst_segment_clip (segment, format, start, stop, &cstart, &cstop))
  goto out_of_segment;

// Convert stream time to running time
rstart = gst_segment_to_running_time (segment, format, cstart);
rstop = gst_segment_to_running_time (segment, format, cstop);

// Also convert to stream time for position reporting
sstart = gst_segment_to_stream_time (segment, format, cstart);
sstop = gst_segment_to_stream_time (segment, format, cstop);
```

### The Synchronization Process

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/libs/gst/base/gstbasesink.c:2665-2828`**

```c
static GstFlowReturn
gst_base_sink_do_sync (GstBaseSink * basesink,
    GstMiniObject * obj, gboolean * late, gboolean * step_end)
{
  GstClockTimeDiff jitter = 0;
  GstClockReturn status = GST_CLOCK_OK;
  GstClockTime rstart, rstop, stime;

  // Get timing information for this object
  syncable = gst_base_sink_get_sync_times (basesink, obj,
      &sstart, &sstop, &rstart, &rstop, &rnext, &do_sync, ...);

  if (!syncable)
    goto not_syncable;  // Events, etc. that don't need sync

  // Store running time for position queries
  priv->current_rstart = rstart;
  priv->current_rstop = (GST_CLOCK_TIME_IS_VALID (rstop) ? rstop : rstart);

again:
  // CRITICAL: Do preroll first
  // In PAUSED state, this blocks until state change to PLAYING
  // This ensures the clock is running before we try to sync
  ret = gst_base_sink_do_preroll (basesink, obj);
  if (G_UNLIKELY (ret != GST_FLOW_OK))
    goto preroll_failed;

  if (!do_sync)
    goto done;  // No sync needed

  // Adjust running time for latency
  stime = gst_base_sink_adjust_time (basesink, rstart);

  GST_DEBUG_OBJECT (basesink, "possibly waiting for clock to reach %"
      GST_TIME_FORMAT ", adjusted %" GST_TIME_FORMAT,
      GST_TIME_ARGS (rstart), GST_TIME_ARGS (stime));

  // CRITICAL: Wait on the clock
  status = gst_base_sink_wait_clock (basesink, stime, &jitter);

  GST_DEBUG_OBJECT (basesink, "clock returned %d, jitter %c%" GST_TIME_FORMAT,
      status, (jitter < 0 ? '-' : ' '), GST_TIME_ARGS (ABS (jitter)));

  // Check if we were interrupted
  if (G_UNLIKELY (basesink->flushing))
    goto flushing;

  // If unscheduled (state change), try preroll again
  if (G_UNLIKELY (status == GST_CLOCK_UNSCHEDULED)) {
    priv->call_preroll = TRUE;
    goto again;
  }

  // Check if buffer is too late (arrived after its presentation time)
  *late = gst_base_sink_is_too_late (basesink, obj, rstart, rstop,
      status, jitter, TRUE);

done:
  return GST_FLOW_OK;
}
```

### The Clock Wait

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/libs/gst/base/gstbasesink.c:2333-2404`**

```c
GstClockReturn
gst_base_sink_wait_clock (GstBaseSink * sink, GstClockTime time,
    GstClockTimeDiff * jitter)
{
  GstClockReturn ret;
  GstClock *clock;
  GstClockTime base_time;

  if (!GST_CLOCK_TIME_IS_VALID (time))
    goto invalid_time;

  GST_OBJECT_LOCK (sink);

  if (!sink->sync)
    goto no_sync;  // Sync disabled

  if ((clock = GST_ELEMENT_CLOCK (sink)) == NULL)
    goto no_clock;  // No clock available

  base_time = GST_ELEMENT_CAST (sink)->base_time;

  GST_LOG_OBJECT (sink,
      "time %" GST_TIME_FORMAT ", base_time %" GST_TIME_FORMAT,
      GST_TIME_ARGS (time), GST_TIME_ARGS (base_time));

  // CRITICAL FORMULA:
  // clock_time = running_time + base_time
  //
  // running_time: Time since stream started (from segment conversion)
  // base_time: Offset to align stream with pipeline clock
  //            Set when pipeline goes to PLAYING
  time += base_time;

  // Create a clock ID for this time
  if (sink->priv->cached_clock_id != NULL) {
    // Reuse existing clock ID for efficiency
    gst_clock_single_shot_id_reinit (clock, sink->priv->cached_clock_id, time);
  } else {
    sink->priv->cached_clock_id = gst_clock_new_single_shot_id (clock, time);
  }

  GST_OBJECT_UNLOCK (sink);

  sink->clock_id = sink->priv->cached_clock_id;

  // Release the preroll lock while waiting
  // This allows state changes to interrupt us
  GST_BASE_SINK_PREROLL_UNLOCK (sink);

  // BLOCKING WAIT on the clock
  // This is where synchronization actually happens!
  ret = gst_clock_id_wait (sink->priv->cached_clock_id, jitter);

  GST_BASE_SINK_PREROLL_LOCK (sink);
  sink->clock_id = NULL;

  return ret;
}
```

### Preroll: The Synchronization Setup

**Code Reference: `/home/user/gstreamer/subprojects/gstreamer/libs/gst/base/gstbasesink.c:2480-2519`**

```c
/**
 * gst_base_sink_do_preroll:
 *
 * If the element is in PAUSED, this function will block until the element
 * goes to PLAYING. This ensures the clock is running before we try to
 * synchronize to it.
 */
GstFlowReturn
gst_base_sink_do_preroll (GstBaseSink * sink, GstMiniObject * obj)
{
  GstFlowReturn ret;

  while (G_UNLIKELY (sink->need_preroll)) {
    GST_DEBUG_OBJECT (sink, "prerolling object %p", obj);

    // Call the preroll vmethod if we have a buffer
    if (sink->priv->call_preroll) {
      GstBaseSinkClass *bclass = GST_BASE_SINK_GET_CLASS (sink);

      if (bclass->prepare)
        if ((ret = bclass->prepare (sink, buf)) != GST_FLOW_OK)
          goto prepare_canceled;

      if (bclass->preroll)
        if ((ret = bclass->preroll (sink, buf)) != GST_FLOW_OK)
          goto preroll_canceled;

      sink->priv->call_preroll = FALSE;
    }

    // Commit state to PAUSED
    if (G_LIKELY (sink->playing_async)) {
      if (G_UNLIKELY (!sink->priv->committed)) {
        // Signal that we're ready for PLAYING
        gst_element_async_state_change_complete (sink);
      }
    }

    // Block here if still need_preroll (in PAUSED)
    // Will be woken up when state changes to PLAYING
    if (G_UNLIKELY (sink->need_preroll)) {
      GST_DEBUG_OBJECT (sink, "waiting for preroll");
      GST_BASE_SINK_PREROLL_WAIT (sink);
    }
  }

  return GST_FLOW_OK;
}
```

## 6. How It All Works Together: Live Pipeline Example

Let's trace a buffer through a live pipeline with a queue:

```
v4l2src (camera) → queue → videosink
```

### Step-by-Step Buffer Flow:

1. **Buffer Creation (v4l2src)**
   - Camera captures frame at time T
   - v4l2src creates buffer with `PTS = T` (e.g., 1.5 seconds)
   - v4l2src sends SEGMENT event: `start=0, rate=1.0, base=0`

2. **Pushing to Queue (v4l2src thread)**
   - `gst_pad_push()` called with buffer
   - Queue's chain function executes in v4l2src's thread
   - Buffer placed in queue's internal list
   - Chain function returns immediately (doesn't wait for display)
   - v4l2src can continue capturing next frame

3. **Queue Buffering**
   - Queue accumulates buffers (decoupling production from consumption)
   - If queue fills up: blocks v4l2src OR drops buffers (depending on leaky mode)
   - Separate thread wakes up when buffers available

4. **Pulling from Queue (queue srcpad thread)**
   - Loop function retrieves buffer from queue
   - Calls `gst_pad_push()` to videosink
   - Buffer still has `PTS = 1.5s`

5. **Synchronization in videosink**
   - videosink chain function receives buffer
   - Calls `gst_base_sink_do_sync()`

   a. **Convert to running time:**
      - Buffer PTS = 1.5s (stream time)
      - Segment: start=0, base=0, rate=1.0
      - running_time = (1.5 - 0) / 1.0 + 0 = 1.5s

   b. **Preroll (if needed):**
      - If in PAUSED, wait here until PLAYING
      - Ensures clock is running

   c. **Calculate clock time:**
      - Pipeline base_time = 100.0s (set when went to PLAYING)
      - clock_time = running_time + base_time = 1.5 + 100.0 = 101.5s

   d. **Wait on clock:**
      - Current clock time: 101.0s
      - Target clock time: 101.5s
      - `gst_clock_id_wait()` blocks for 0.5 seconds
      - Thread sleeps...

   e. **Clock reaches target:**
      - Clock now at 101.5s
      - `gst_clock_id_wait()` returns GST_CLOCK_OK
      - jitter = 0 (on time)

   f. **Render:**
      - videosink's render vmethod called
      - Frame displayed on screen

6. **Next Buffer**
   - Process repeats for buffer with PTS = 1.533s (30fps)
   - running_time = 1.533s
   - clock_time = 101.533s
   - Waits 0.033s from previous frame

### Why Queue is Critical in Live Pipelines:

**Without Queue:**
```
v4l2src → videosink (same thread)
```
- v4l2src captures frame
- Pushes to videosink (chain call)
- videosink waits on clock (blocks)
- v4l2src can't capture next frame until wait finishes
- Camera buffer might overflow!

**With Queue:**
```
v4l2src (thread A) → queue → videosink (thread B)
```
- v4l2src captures frame (thread A)
- Pushes to queue, returns immediately
- v4l2src continues capturing
- videosink waits on clock in separate thread B
- No blocking of capture!

### Live vs Non-Live Pipelines:

**Non-Live (e.g., file playback):**
```
filesrc → decodebin → videosink
```
- Timestamps in file might start at 0 or arbitrary value
- Pipeline can pause/seek
- Running time controls playback speed
- Synchronization ensures smooth playback at correct rate

**Live (e.g., camera, network stream):**
```
v4l2src → queue → videosink
```
- Timestamps represent real capture time
- Cannot pause source (camera keeps running)
- Must drop frames if can't keep up
- Synchronization ensures frames display at correct moment
- Latency matters: `base_time` adjusted for acceptable delay

## 7. Key Timing Concepts Summary

### Timestamp Types:

1. **Stream Time (PTS/DTS)**
   - Set by source element
   - Represents time in the content
   - Example: 0s, 1s, 2s, ... in a video file

2. **Running Time**
   - Converted from stream time via segment
   - Always increasing (resets on flush)
   - Used for synchronization
   - Formula: `running_time = (stream_time - segment.start) / segment.rate + segment.base`

3. **Clock Time**
   - Absolute time on the pipeline clock
   - Formula: `clock_time = running_time + base_time`
   - What we actually wait for in `gst_clock_id_wait()`

4. **Base Time**
   - Set when pipeline goes to PLAYING
   - Offset to align stream with clock
   - Allows multiple streams to sync together

### The Synchronization Formula:

```
Buffer PTS (stream time)
    ↓ (gst_segment_to_running_time)
Running Time
    ↓ (+ base_time)
Clock Time
    ↓ (gst_clock_id_wait)
WAIT until clock reaches this time
    ↓
RENDER
```

## 8. Special Cases and Edge Conditions

### Buffers Arriving Late:

If clock time already passed when we try to wait:
- `gst_clock_id_wait()` returns immediately with `jitter < 0`
- Buffer marked as "late"
- `max-lateness` property determines if buffer is dropped
- QoS events sent upstream to reduce quality/rate

### Flushing:

During seeks or state changes:
- Queue drains all buffers
- Clock waits are interrupted
- FLUSH events reset running_time

### Synchronization Disabled:

Some elements set `sync=false`:
- No clock waiting
- Buffers rendered as fast as possible
- Used for testing, file writing, etc.

### Multiple Sinks:

Multiple sinks (audio + video):
- Share same pipeline clock
- Same base_time
- Synchronize to each other via clock
- If audio sink provides clock, video syncs to audio timing

## 9. Code Reference Summary

| Component | File | Key Lines | Purpose |
|-----------|------|-----------|---------|
| Chain calls | gstpad.c | 4497-4586 | Buffer passing mechanism |
| Buffer timestamps | gstbuffer.h | 80-133 | PTS/DTS/Duration definitions |
| Segment conversion | gstsegment.c | 822-867 | Stream time → Running time |
| Queue chain | gstqueue.c | 1271-1376 | Buffering (upstream thread) |
| Queue loop | gstqueue.c | 1590-1639 | Pushing (downstream thread) |
| BaseSink sync | gstbasesink.c | 2665-2828 | Main synchronization logic |
| Clock wait | gstbasesink.c | 2333-2404 | Actual blocking on clock |
| Preroll | gstbasesink.c | 2480-2519 | PAUSED→PLAYING coordination |
| Get sync times | gstbasesink.c | 2147-2258 | Extract and convert timestamps |

## Conclusion

GStreamer's synchronization is elegant and robust:

1. **Timestamps flow with buffers** - Set once by source, preserved through pipeline
2. **Segments define time domains** - Enable seeking, rate changes, accumulation
3. **Queues decouple threads** - Critical for live sources to prevent blocking
4. **BaseSink coordinates sync** - Preroll ensures clock running, then waits
5. **Clock provides timing** - Shared clock enables multi-sink synchronization

The key insight: **synchronization happens at sinks, not during data flow**. Buffers flow through the pipeline as fast as possible (only throttled by queue limits), but sinks wait on the clock before rendering. This design maximizes throughput while maintaining precise timing.
