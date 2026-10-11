"""No-network regression tests for Discord voice receiver lifecycle."""
from types import SimpleNamespace as NS
from voice_conversation.receive import ReceiveBackend


def backend(*, started=True, connected=True, listening=True):
    b = ReceiveBackend(lambda: {1})
    b.vc = NS(is_connected=lambda: connected, is_listening=lambda: listening)
    b.active = True
    b.reader_started = started
    return b


def test_connection_alive_but_receiver_stopped_is_unhealthy():
    assert backend(listening=False).unhealthy()


def test_healthy_reader_and_idle_silence_are_not_failures():
    assert not backend().unhealthy()


def test_unexpected_callback_without_exception_marks_failed():
    b = backend()
    b.reader_finished(None)
    assert b.failed and b.unhealthy()
    assert b.metrics["reader_exited_unexpectedly"] == 1


def test_deliberate_stop_callback_does_not_set_failure():
    b = backend()
    b.active = False
    b.reader_started = False
    b.reader_finished(None)
    assert not b.failed
    assert b.metrics["reader_exited_unexpectedly"] == 0
    assert not b.unhealthy()


def test_prestart_does_not_false_alarm_on_listener_state():
    assert not backend(started=False, listening=False).unhealthy()


def test_disconnection_still_detected_without_started_reader():
    assert backend(started=False, connected=False).unhealthy()
