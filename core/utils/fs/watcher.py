from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from typing import Callable
import threading

class WatcherHandler(FileSystemEventHandler):

    def __init__ ( self, callback: Callable, watch_dirs: bool = True, delay: float = 0.3 ):

        self.callback   = callback
        self.watch_dirs = watch_dirs
        self.delay      = delay
        self.timers     = {}

    def _cleanup_ ( self ):

        for key, timer in list(self.timers.items()):
            if not timer.is_alive(): del self.timers[key]

        return self

    def _debounce_ ( self, key: str, func: Callable ):

        if key in self.timers: self.timers[key].cancel()
        timer = threading.Timer(self.delay, func)

        self.timers[key] = timer
        timer.start()

        return self._cleanup_()

    def _trigger_ ( self, event_type: str, event ):

        if not self.watch_dirs and event.is_directory: return

        src = event.src_path
        dest = getattr(event, "dest_path", None)

        return self._debounce_(src, lambda: self.callback(event_type, src, dest))

    def on_modified ( self, event ):

        return self._trigger_('modified', event)

    def on_created ( self, event ):

        return self._trigger_('created', event)

    def on_deleted ( self, event ):

        return self._trigger_('deleted', event)

    def on_moved ( self, event ):

        return self._trigger_('moved', event)

class Watcher:

    def __init__ ( self, path: str, callback: Callable, watch_dirs: bool = True, delay: float = 0.3 ):

        self.path       = path
        self.callback   = callback
        self.watch_dirs = watch_dirs
        self.delay      = delay
        self.thread     = None
        self.observer   = Observer()
        self.stop_event = threading.Event()

    def work ( self ):

        event_handler = WatcherHandler(self.callback, self.watch_dirs, self.delay)
        self.observer.schedule(event_handler, self.path, recursive=True)
        self.observer.start()

        while not self.stop_event.is_set():
            self.stop_event.wait(1)

        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()

    def start ( self ):

        if self.thread: return self

        self.thread = threading.Thread(target=self.work)
        self.thread.start()

        return self

    def stop ( self ):

        if not self.thread: return

        self.stop_event.set()
        self.thread.join()
        self.thread = None
