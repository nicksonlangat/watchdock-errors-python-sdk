from watchdock_errors.utils import extract_stacktrace


def _boom():
    # This line and the two on either side are what the context capture should
    # pick up. Keep the surrounding lines stable so the assertions below hold.
    x = 1
    raise ValueError("boom")  # <-- failing line
    return x


def test_extract_stacktrace_captures_source_context():
    try:
        _boom()
    except ValueError as exc:
        frames = extract_stacktrace(exc)

    assert frames, "expected at least one frame"

    # The frame for _boom is the one whose failing line raised.
    boom_frame = next(f for f in frames if f["function"] == "_boom")

    assert boom_frame["context_line"] == 'raise ValueError("boom")  # <-- failing line'
    # Two lines before and two after, in order, with indentation preserved.
    assert len(boom_frame["pre_context"]) == 2
    assert len(boom_frame["post_context"]) == 2
    # The line immediately before the raise is `x = 1` (indentation kept).
    assert boom_frame["pre_context"][1] == "    x = 1"
    # The line immediately after the raise is the return.
    assert boom_frame["post_context"][0] == "    return x"


def test_frames_always_have_context_keys():
    try:
        raise KeyError("missing")
    except KeyError as exc:
        frames = extract_stacktrace(exc)

    for frame in frames:
        assert "context_line" in frame
        assert "pre_context" in frame
        assert "post_context" in frame
        assert isinstance(frame["pre_context"], list)
        assert isinstance(frame["post_context"], list)
