from agent.state import RunCache


def test_get_or_compute_only_calls_compute_once_per_key():
    cache = RunCache()
    calls = []

    def compute():
        calls.append(1)
        return "result"

    first = cache.get_or_compute(("k",), compute)
    second = cache.get_or_compute(("k",), compute)

    assert first == "result"
    assert second == "result"
    assert len(calls) == 1


def test_different_keys_each_compute_independently():
    cache = RunCache()
    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    a = cache.get_or_compute(("a",), compute)
    b = cache.get_or_compute(("b",), compute)

    assert a == 1
    assert b == 2
