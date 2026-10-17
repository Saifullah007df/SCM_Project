"""Reentrant thread + POSIX process locks for a shared local demo workspace."""
import fcntl
import os
import threading


class FileLock:
    def __init__(self, path):
        self.path = path
        self.mutex = threading.RLock()
        self.local = threading.local()

    def __enter__(self):
        self.mutex.acquire()
        depth = getattr(self.local, 'depth', 0)
        try:
            if depth == 0:
                self.local.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                fcntl.flock(self.local.fd, fcntl.LOCK_EX)
            self.local.depth = depth + 1
            return self
        except BaseException:
            self.mutex.release()
            raise

    def __exit__(self, *_):
        self.local.depth -= 1
        if self.local.depth == 0:
            fcntl.flock(self.local.fd, fcntl.LOCK_UN)
            os.close(self.local.fd)
        self.mutex.release()
