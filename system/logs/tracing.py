"""重大度(INFO/WARN/ERROR)と詳細度(1/2/3)を独立して管理する。"""

import inspect
import logging
from functools import partialmethod, wraps
from pathlib import Path
from reprlib import Repr


class DetailLogger(logging.Logger):
    detail = 1

    def enabled(self, detail):
        return detail <= self.detail

    def emit_detail(self, severity, detail, message, *args, **kwargs):
        if self.enabled(detail):
            label = {logging.INFO: "INFO", logging.WARNING: "WARN",
                     logging.ERROR: "ERROR"}[severity]
            self.log(severity, message, *args,
                     extra={"label": f"{label}{detail}"}, **kwargs)

    info1 = partialmethod(emit_detail, logging.INFO, 1)
    info2 = partialmethod(emit_detail, logging.INFO, 2)
    info3 = partialmethod(emit_detail, logging.INFO, 3)
    warn1 = partialmethod(emit_detail, logging.WARNING, 1)
    warn2 = partialmethod(emit_detail, logging.WARNING, 2)
    warn3 = partialmethod(emit_detail, logging.WARNING, 3)
    error1 = partialmethod(emit_detail, logging.ERROR, 1)
    error2 = partialmethod(emit_detail, logging.ERROR, 2)
    error3 = partialmethod(emit_detail, logging.ERROR, 3)


logger = DetailLogger("dungeon", logging.INFO)
logger.propagate = False
logger.addHandler(logging.NullHandler())
_repr = Repr()
_repr.maxother = 300
_repr.maxstring = 160
_previous_calls = set()
_current_calls = set()


def reset_trace_calls():
    _previous_calls.clear()
    _current_calls.clear()


def begin_trace_frame():
    """前フレームから続く同じメソッドは再出力しない。"""
    _previous_calls.clear()
    _previous_calls.update(_current_calls)
    _current_calls.clear()


def configure_logging(detail=1):
    if detail not in (1, 2, 3):
        raise ValueError("ログの詳細度は1・2・3を指定してください")
    logger.detail = detail
    reset_trace_calls()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    log_dir = Path(__file__).resolve().parent
    log_dir.mkdir(exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(
        log_dir / "game.log", mode="w", encoding="utf-8")]
    for handler in handlers:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(label)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)


def trace_method(method, detail):
    signature = inspect.signature(method)

    @wraps(method)
    def wrapped(*args, **kwargs):
        key = (id(args[0]) if args else None, method.__qualname__, logger.detail)
        first = key not in _current_calls and key not in _previous_calls
        _current_calls.add(key)
        if first and detail == 2:
            logger.info1("CALL %s", method.__qualname__)
        if first and logger.enabled(detail):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = ", ".join(
                f"{name}={_repr.repr(value)}"
                for name, value in bound.arguments.items() if name != "self")
            logger.emit_detail(logging.INFO, detail, "CALL %s(%s)",
                               method.__qualname__, arguments)
        try:
            result = method(*args, **kwargs)
        except Exception as error:
            # 通常はクラス名だけ。メソッドと例外詳細は指定時のみ。
            logger.error1("FAILED %s", method.__qualname__.split(".")[0])
            logger.error2("RAISE %s: %s", method.__qualname__, type(error).__name__)
            logger.error3("例外詳細", exc_info=True)
            raise
        if first and logger.enabled(detail):
            logger.emit_detail(logging.INFO, detail, "RETURN %s -> %s",
                               method.__qualname__, _repr.repr(result))
        return result
    return wrapped


def trace_class(*, info_methods=()):
    """通常メソッドは2、頻繁な描画・座標参照は3で記録する。"""
    def decorate(cls):
        for name, member in list(vars(cls).items()):
            detail = 2 if name in info_methods else 3
            if inspect.isfunction(member):
                setattr(cls, name, trace_method(member, detail))
            elif isinstance(member, property) and member.fget is not None:
                setattr(cls, name, property(trace_method(member.fget, 3),
                                            member.fset, member.fdel, member.__doc__))
        return cls
    return decorate
