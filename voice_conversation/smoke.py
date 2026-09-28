"""Validate an owner-exported health snapshot; requires human verification too."""

import argparse
import json
from pathlib import Path


def evaluate(snapshot, speech_confirmed=False, stop_confirmed=False):
    metrics = snapshot.get("metrics", {})
    failures = []
    for key in (
        "packets",
        "dave_frames",
        "pcm_frames",
        "vad_segments",
        "stt_success",
        "spoken_chunks",
        "cancelled_responses",
    ):
        if metrics.get(key, 0) < 1:
            failures.append("Missing evidence: " + key)
    if not 20 <= metrics.get("rms_peak", 0) < 32767:
        failures.append("PCM levels need inspection")
    if not speech_confirmed:
        failures.append("Human must confirm a known phrase was understood correctly")
    if not stop_confirmed:
        failures.append(
            "Human must confirm audible playback stopped without resuming stale audio"
        )
    if not snapshot.get("listening"):
        failures.append("Receiver is not currently active")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--speech-confirmed", action="store_true")
    parser.add_argument("--stop-confirmed", action="store_true")
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.snapshot.read_text()),
        args.speech_confirmed,
        args.stop_confirmed,
    )
    print(
        "\n".join(result)
        if result
        else "Evidence checklist passed; retain operator observations with this snapshot."
    )
    raise SystemExit(bool(result))


if __name__ == "__main__":
    main()
