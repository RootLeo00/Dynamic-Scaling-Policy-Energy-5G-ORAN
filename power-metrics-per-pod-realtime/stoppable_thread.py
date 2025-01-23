from threading import Event, Thread
class StoppableThread(Thread):
    """
    A thread class that stops gracefully using a stop event.
    """
    def __init__(self, *args, stop_event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_event = stop_event or Event()

    def run(self):
        if hasattr(self, "_target") and self._target:
            try:
                self._target(*self._args, **self._kwargs)
            except Exception as e:
                print(f"Exception in thread {self.name}: {e}")
            finally:
                self.stop_event.set()