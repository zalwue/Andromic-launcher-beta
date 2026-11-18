class Reporter:
    """Carries log, status and progress callbacks so the core stays UI-agnostic."""

    def __init__(self, log=None, status=None, progress=None):
        self._log = log
        self._status = status
        self._progress = progress

    def log(self, message: str) -> None:
        if self._log:
            self._log(message)

    def status(self, message: str) -> None:
        if self._status:
            self._status(message)

    def progress(self, done: int, total: int, label: str = "") -> None:
        if self._progress:
            self._progress(done, total, label)
