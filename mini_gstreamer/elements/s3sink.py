"""
S3Sink: Uploads segments to S3

Like any sink element (filesink, s3sink, etc.), this element:
- Has only a sink pad (no source pads)
- Receives buffers via chain function
- Performs final processing (upload to S3)
- Returns flow result

This is the end of the call chain!
"""

import logging
import json
from typing import Optional

from ..core import (
    Element, Buffer, BufferFlags, Pad, PadDirection, FlowReturn,
    State, StateChange, StateChangeReturn
)

logger = logging.getLogger(__name__)


class S3Sink(Element):
    """
    Sink element that uploads segments to S3.

    Like GstBaseSink, this:
    - Has only a sink pad
    - Receives data via chain function
    - Performs final operation (S3 upload)
    - Returns flow result back up the stack
    """

    def __init__(self, name: str, bucket: str, prefix: str = "live/",
                 simulate: bool = True):
        super().__init__(name)

        self.bucket = bucket
        self.prefix = prefix
        self.simulate = simulate  # If True, just log instead of actually uploading
        self.segments_uploaded = 0

        # S3 client (would be boto3 in real implementation)
        self.s3_client = None

        # Create sink pad (input only)
        self.sink_pad = Pad("sink", PadDirection.SINK, self)
        self.add_pad(self.sink_pad)

        # Register chain function
        self.sink_pad.set_chain_function(self._chain)

    def change_state(self, transition: StateChange) -> StateChangeReturn:
        """Handle state changes"""
        if transition == StateChange.NULL_TO_READY:
            # Initialize S3 client
            if not self.simulate:
                try:
                    import boto3
                    self.s3_client = boto3.client('s3')
                    logger.info(f"{self.name} - S3 client initialized for bucket: {self.bucket}")
                except ImportError:
                    logger.warning(f"{self.name} - boto3 not available, running in simulation mode")
                    self.simulate = True
                except Exception as e:
                    logger.error(f"{self.name} - Failed to initialize S3 client: {e}")
                    return StateChangeReturn.FAILURE
            else:
                logger.info(f"{self.name} - Running in SIMULATION mode (no actual S3 uploads)")

        return super().change_state(transition)

    def _chain(self, pad: Pad, buffer: Buffer) -> FlowReturn:
        """
        Chain function for the sink.

        This is THE END of the call chain!
        After we process the buffer, we return back up the stack.
        """
        logger.info(f"      {self.name}.chain() - RECEIVED {buffer}")

        # Check for EOS
        if buffer.has_flags(BufferFlags.EOS):
            logger.info(f"      {self.name}.chain() - Got EOS")
            logger.info(f"      {self.name} - Total segments uploaded: {self.segments_uploaded}")
            logger.info(f"      {self.name}.chain() - RETURNING EOS to caller")
            return FlowReturn.EOS

        # Upload the segment
        ret = self._upload_segment(buffer)

        logger.info(f"      {self.name}.chain() - Upload complete, RETURNING {ret.name} to caller")

        # This return value bubbles all the way back up the stack!
        return ret

    def _upload_segment(self, buffer: Buffer) -> FlowReturn:
        """
        Upload segment to S3.

        In real implementation, this would use boto3 to upload.
        Here we simulate or actually upload depending on configuration.
        """
        data = buffer.data

        if data.get("type") != "hls_segment":
            logger.warning(f"      {self.name} - Expected HLS segment, got {data.get('type')}")
            return FlowReturn.OK

        segment_number = data.get("segment_number", 0)
        filename = data.get("filename", f"segment_{segment_number:06d}.ts")
        duration = data.get("duration", 0.0)
        buffer_count = data.get("buffer_count", 0)

        # Construct S3 key
        s3_key = f"{self.prefix}{filename}"

        logger.info(f"\n      {self.name} - UPLOADING SEGMENT:")
        logger.info(f"      Segment: #{segment_number}")
        logger.info(f"      Duration: {duration:.2f}s")
        logger.info(f"      Buffers: {buffer_count}")
        logger.info(f"      S3 Location: s3://{self.bucket}/{s3_key}")

        if self.simulate:
            # Simulate upload
            logger.info(f"      [SIMULATED] Upload successful")
            self._write_segment_to_disk(filename, data)
        else:
            # Actually upload to S3
            try:
                # In real code, we'd serialize the segment data properly
                segment_bytes = json.dumps(data, indent=2).encode('utf-8')

                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=segment_bytes,
                    ContentType='application/json'
                )
                logger.info(f"      [REAL] Upload successful")
            except Exception as e:
                logger.error(f"      {self.name} - Upload failed: {e}")
                return FlowReturn.ERROR

        self.segments_uploaded += 1
        logger.info(f"      Total segments uploaded: {self.segments_uploaded}\n")

        return FlowReturn.OK

    def _write_segment_to_disk(self, filename: str, data: dict):
        """
        Write segment to local disk for inspection (simulation mode).
        """
        try:
            import os
            output_dir = "/tmp/mini-gstreamer-segments"
            os.makedirs(output_dir, exist_ok=True)

            filepath = os.path.join(output_dir, filename.replace('.ts', '.json'))

            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"      Segment saved to: {filepath}")
        except Exception as e:
            logger.warning(f"      Could not save segment to disk: {e}")
