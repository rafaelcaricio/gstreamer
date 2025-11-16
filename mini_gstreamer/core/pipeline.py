"""
Pipeline: Top-level container for elements

The Pipeline is a special bin that manages:
- Global state changes for all child elements
- Clock management (simplified here)
- Overall timing and synchronization
"""

from typing import List
import logging

from .element import Element, State, StateChangeReturn, StateChange
from .pad import Pad

logger = logging.getLogger(__name__)


class Pipeline(Element):
    """
    Pipeline is the top-level container.

    Like GstPipeline, it:
    - Manages state transitions for all children
    - Provides timing coordination
    - Acts as the root of the element hierarchy
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.elements: List[Element] = []
        self.start_time: float = 0.0  # When pipeline started playing

    def add(self, *elements: Element) -> bool:
        """
        Add elements to the pipeline.

        Like gst_bin_add() in GStreamer.
        """
        for element in elements:
            if element in self.elements:
                logger.warning(f"{self.name} - Element {element.name} already in pipeline")
                continue

            self.elements.append(element)
            logger.info(f"{self.name} - Added element: {element.name}")

        return True

    def remove(self, element: Element) -> bool:
        """Remove an element from the pipeline"""
        if element in self.elements:
            self.elements.remove(element)
            logger.info(f"{self.name} - Removed element: {element.name}")
            return True
        return False

    def get_element(self, name: str) -> Element:
        """Get element by name"""
        for element in self.elements:
            if element.name == name:
                return element
        return None

    def set_state(self, new_state: State) -> StateChangeReturn:
        """
        Set pipeline state, which sets state on all child elements.

        Like gst_element_set_state() for a pipeline in GStreamer.
        The pipeline coordinates state changes across all elements.
        """
        if new_state == self.state:
            return StateChangeReturn.SUCCESS

        logger.info(f"\n{'='*60}")
        logger.info(f"PIPELINE {self.name}: {self.state.name} -> {new_state.name}")
        logger.info(f"{'='*60}")

        # Change state on all children first
        for element in self.elements:
            ret = element.set_state(new_state)
            if ret == StateChangeReturn.FAILURE:
                logger.error(f"Pipeline state change failed at element {element.name}")
                return StateChangeReturn.FAILURE

        # Then change our own state
        ret = super().set_state(new_state)

        # Track when we start playing
        if new_state == State.PLAYING and ret in (StateChangeReturn.SUCCESS, StateChangeReturn.NO_PREROLL):
            import time
            self.start_time = time.time()
            logger.info(f"Pipeline PLAYING - Start time: {self.start_time}")

        logger.info(f"{'='*60}\n")
        return ret

    def change_state(self, transition: StateChange) -> StateChangeReturn:
        """Handle pipeline-specific state changes"""
        # Let parent class handle pad activation
        return super().change_state(transition)

    def get_pipeline_time(self) -> float:
        """
        Get current pipeline time (simplified).

        In real GStreamer, this would use the pipeline clock.
        """
        if self.state != State.PLAYING:
            return 0.0

        import time
        return time.time() - self.start_time

    def __repr__(self) -> str:
        element_names = [e.name for e in self.elements]
        return f"Pipeline({self.name}, state={self.state.name}, elements={element_names})"
