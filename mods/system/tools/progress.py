"""What the dev tools are doing right now, for the Claude Code status line (.claude/statusline.py shows it).

    import progress; progress.set("dev test", 2, 6, "live-fast, session-fast"); ...; progress.clear()

One small file in the temp folder (dqix-status.json): the job, done / total, the current stage, when it started, and the
writer's process id (the status line drops the badge once that process is gone). Never raises: a status is a nicety.
"""
import json, os, tempfile, time

PATH = os.path.join(tempfile.gettempdir(), "dqix-status.json")
_started = {}


def set(what, done=None, total=None, stage=""):
    t0 = _started.setdefault(what, time.time())
    try:
        tmp = PATH + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(what=what, done=done, total=total, stage=stage, since=t0, t=time.time(), pid=os.getpid()), f)
        os.replace(tmp, PATH)
    except OSError:
        pass


def clear():
    try:
        with open(PATH, encoding="utf-8") as f:
            mine = json.load(f).get("pid") == os.getpid()
        if mine:
            os.remove(PATH)
    except (OSError, ValueError):
        pass
