"""Offline crash-replay reference model; NOT the installed SQS implementation.

The model documents at-least-once transport and idempotent application processing.
No network calls, secrets, production imports, or exchange interaction.
"""
from dataclasses import dataclass, field


@dataclass
class ReplayModel:
    pending: set[str] = field(default_factory=set)
    delivered: list[str] = field(default_factory=list)
    processed: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)

    def stage(self, signal_id: str):
        self.pending.add(signal_id)

    def send(self, signal_id: str):
        if signal_id not in self.pending:
            raise ValueError("not staged")
        self.delivered.append(signal_id)

    def mark_sent(self, signal_id: str):
        if signal_id not in self.delivered:
            raise ValueError("not sent")
        self.pending.discard(signal_id)

    def consume(self, signal_id: str, *, succeed: bool):
        if signal_id not in self.delivered:
            raise ValueError("not delivered")
        if not succeed:
            return False
        self.processed.add(signal_id)
        self.deleted.add(signal_id)
        return True


def test_crash_before_send_preserves_retry():
    model = ReplayModel()
    model.stage("research-a")
    assert "research-a" in model.pending
    model.send("research-a")
    model.mark_sent("research-a")
    assert model.delivered == ["research-a"]


def test_crash_after_send_can_duplicate_transport_but_not_effect():
    model = ReplayModel()
    model.stage("research-a")
    model.send("research-a")
    # Crash before marking sent; retry is allowed.
    model.send("research-a")
    assert model.delivered == ["research-a", "research-a"]
    assert model.consume("research-a", succeed=True)
    assert model.consume("research-a", succeed=True)
    assert model.processed == {"research-a"}


def test_transient_failure_must_not_delete_message():
    model = ReplayModel()
    model.stage("research-a")
    model.send("research-a")
    assert not model.consume("research-a", succeed=False)
    assert "research-a" not in model.deleted
    assert model.consume("research-a", succeed=True)
    assert "research-a" in model.deleted


def test_unknown_delivery_cannot_be_processed():
    model = ReplayModel()
    try:
        model.consume("research-unknown", succeed=True)
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected acceptance")
    assert not model.processed
