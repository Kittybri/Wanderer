"""Focused contracts for attribution and selective Discord notification."""
from partner_banter_routing import TurnEnvelope, authorized_ping_ids


def test_turn_envelope_keeps_primary_speaker_and_secondary_romance_user_separate():
    turn = TurnEnvelope(source_message_id=100, channel_id=20, speaker_id=99,
                        speaker_kind="wanderer", addressee_id=99,
                        addressee_kind="wanderer", romance_target_id=77)
    assert turn.speaker_id == turn.addressee_id == 99
    assert authorized_ping_ids(turn, romance_ping_selected=False) == frozenset({99})
    assert authorized_ping_ids(turn, romance_ping_selected=True) == frozenset({77, 99})


def test_explicit_targets_are_kept_without_authorizing_arbitrary_model_ids():
    turn = TurnEnvelope(source_message_id=10, channel_id=20, speaker_id=99,
                        speaker_kind="scaramouche", addressee_id=99,
                        addressee_kind="scaramouche",
                        explicit_human_target_ids=frozenset({42}), romance_target_id=77)
    assert authorized_ping_ids(turn) == frozenset({42, 99})
    assert 123456 not in authorized_ping_ids(turn, romance_ping_selected=True)



def test_turn_authority_is_structured_and_rejects_mismatched_ids():
    from partner_banter_routing import authoritative_turn_context, coherent_partner_reply
    valid = TurnEnvelope(source_message_id=99, channel_id=20, speaker_id=123,
                         speaker_kind="wanderer", addressee_id=123,
                         addressee_kind="wanderer", romance_target_id=77)
    context = authoritative_turn_context(valid)
    assert "message_id=99" in context and "primary_addressee=wanderer" in context
    assert coherent_partner_reply("Wanderer, stop.", "Wanderer", turn=valid)
    wrong = TurnEnvelope(source_message_id=99, channel_id=20, speaker_id=123,
                         speaker_kind="wanderer", addressee_id=77,
                         addressee_kind="human", romance_target_id=77)
    assert coherent_partner_reply("Wrong speaker.", "Wanderer", turn=wrong) == ""
    import pytest
    with pytest.raises(ValueError):
        authoritative_turn_context(wrong)
