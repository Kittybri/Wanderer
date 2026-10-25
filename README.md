<div align="center">

<img src="assets/wanderer-banner-v2.webp" alt="Wanderer in blue and white" width="100%">

# Wanderer

**A conversational Discord agent with memory, voice, and media workflows**

A Python project exploring persistent conversation, contextual responses, and coordination with [Scaramouche](https://github.com/Kittybri/Scaramouche).

</div>

## Engineering overview

Wanderer combines a fictional character interface with a deployed conversational application. The engineering includes Discord event handling, persistent user state, provider-backed generation, output repetition controls, optional voice and document workflows, and diagnosis of failures across those boundaries.

**Start here:** [architecture](docs/architecture.md) | [setup and tests](docs/quickstart.md) | [repair tasks](https://github.com/Kittybri/agent-repair-lab) | [contribution and AI assistance](https://github.com/Kittybri/agent-repair-lab/blob/main/CONTRIBUTIONS.md)

## What to inspect

| Area | Source or evidence |
| --- | --- |
| Event and command orchestration | `bot.py` |
| User state and conversation persistence | `memory.py` and `memory_rebuild.py` |
| Relationship context | `relationship_engine.py` |
| Response repetition controls | `anti_repeat.py` and [offline regression tests](tests/test_anti_repeat.py) |
| Optional voice and document integrations | `voice_handler.py` and `google_docs_bridge.py` |
| Video workflow boundary | `video_reports.py` and `video_render_worker.py` |
| A real production diagnosis | [PDF retrieval case study](https://github.com/Kittybri/agent-repair-lab/blob/main/docs/pdf-retrieval.md) |
| A testable coordination design | [Turn ownership case study](https://github.com/Kittybri/agent-repair-lab/blob/main/docs/turn-ownership.md) |

## Run the offline checks

```sh
python -m unittest discover -s tests -v
```

These standard-library tests cover user-visible repetition behavior and isolation between the characters' recent output histories. GitHub Actions runs them on Python 3.11 and 3.12 without credentials. They do not measure model accuracy or establish complete production coverage.

The [quickstart](docs/quickstart.md) separates offline checks from live bot setup. For an inspectable engineering demonstration without running a Discord service, use the five-task [repair lab](https://github.com/Kittybri/agent-repair-lab).

## Character experience

Wanderer is dry, observant, and reluctant to show warmth. Persistent familiarity, creative conversation, games, and optional media support that experience. The fictional character's claims about remembering or understanding are not guarantees about the model.

## Status and limitations

Public source and deployed releases have historically diverged. The architecture document maps this repository, and each case study states its evidence. The repair tasks are synthetic reproductions with explicit contracts. There are no published latency, uptime, accuracy, or model-comparison results.

This is an AI-assisted project directed by Abriana Meazzo. Coding agents assisted implementation, debugging, testing, and documentation. The [contribution statement](https://github.com/Kittybri/agent-repair-lab/blob/main/CONTRIBUTIONS.md) distinguishes project direction from assisted implementation.

Fan-made Genshin Impact character project, not affiliated with HoYoverse. Character imagery and names belong to their respective owners.

[Privacy policy](PRIVACY.md) | [Development notes](CONTRIBUTING.md)
