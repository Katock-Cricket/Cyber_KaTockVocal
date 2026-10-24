from katock.adapters.proc import take_lines


def test_progress_carriage_return_is_a_line() -> None:
    pending = bytearray(b"progress 1%\rprogress 100%\n")
    assert take_lines(pending, final=False) == ["progress 1%", "progress 100%"]
    assert pending == bytearray()


def test_trailing_carriage_return_waits_for_more() -> None:
    pending = bytearray(b"progress 40%\r")
    assert take_lines(pending, final=False) == []
    pending.extend(b"\nnext")
    assert take_lines(pending, final=True) == ["progress 40%", "next"]


def test_long_progress_does_not_need_newline() -> None:
    chunk = b"#" * 200_000
    pending = bytearray(b"start\r" + chunk + b"\rdone")
    lines = take_lines(pending, final=True)
    assert lines[0] == "start"
    assert lines[-1] == "done"
    assert sum(len(line) for line in lines) == 5 + 200_000 + 4
