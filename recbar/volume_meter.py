"""Real-time mic volume meter via OBS InputVolumeMeters events.

No longer a separate thread with its own WebSocket connection.
Now just a callback handler registered with the shared OBSConnection.
The connection's reader thread calls on_event() when volume data arrives.
"""

from .config import MIC_NAME


class VolumeMeter:
    """Processes InputVolumeMeters events from the shared OBS connection.

    Register this as the event_callback on OBSConnection. It filters for
    the configured mic input and updates state.mic_level + mic_history.
    """

    def __init__(self, state):
        self.state = state

    def on_event(self, event_data):
        """Called by OBSConnection reader thread for every OBS event.

        Filters for InputVolumeMeters and extracts peak level for
        the configured mic input.
        """
        if event_data.get("eventType") != "InputVolumeMeters":
            return

        for inp in event_data.get("eventData", {}).get("inputs", []):
            if inp.get("inputName") != MIC_NAME:
                continue
            levels = inp.get("inputLevelsMul", [[0, 0, 0]])
            if levels and levels[0]:
                # [magnitude, peak, inputPeak] — use peak
                peak = levels[0][1] if len(levels[0]) > 1 else levels[0][0]
                self.state.mic_level = max(0.0, min(1.0, float(peak)))
                self.state.mic_history.append(self.state.mic_level)
