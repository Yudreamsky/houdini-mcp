"""Stop a tool call's waiting loops when the client cancels it.

Tool bodies run in worker threads (see server.tool), so a cancelled call cannot be interrupted from outside: its
thread carries a flag in a context variable, and every loop that waits on Houdini, a renderer or a pause checks it.
Outside a tool call (tests, scripts, the hython worker) there is no flag and nothing is ever cancelled."""
import contextvars
import threading
import time


class Cancelled(BaseException):
    """The client cancelled this call. Not an Exception, so retry and cleanup code that catches errors lets it pass."""


FLAG = contextvars.ContextVar("houdini_research_cancel", default=None)


def requested():
    flag = FLAG.get()
    return flag is not None and flag.is_set()


def check():
    if requested():
        raise Cancelled("The client cancelled this call")


def wait(seconds):
    """Sleep, ending at once with Cancelled when the call is cancelled."""
    flag = FLAG.get()
    if flag is None:
        time.sleep(seconds)
    elif flag.wait(seconds):
        raise Cancelled("The client cancelled this call")


def run(flag, call, *args, **kwargs):
    """Call a tool body in this thread under a cancel flag."""
    FLAG.set(flag)
    return call(*args, **kwargs)


def new_flag():
    return threading.Event()
