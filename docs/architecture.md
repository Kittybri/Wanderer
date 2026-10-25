# Architecture and evidence map

Wanderer is a Python Discord bot with persistent user state, provider-backed generation, optional voice and media, and interaction with Scaramouche. This diagram maps the published repository; it is not a claim that every feature from a newer deployed release is present here.

```mermaid
flowchart TD
    D[Discord events and commands] --> B[bot.py: orchestration]
    B <--> M[memory.py: persistent user and conversation state]
    B --> R[relationship_engine.py: context and behavior rules]
    B --> A[anti_repeat.py: recent-output policy]
    B --> G[Groq: response generation]
    B --> V[voice_handler.py: voice output]
    B --> C[google_docs_bridge.py: document integration]
    B --> Q[video_reports.py: video requests]
    Q --> W[video_render_worker.py: rendering boundary]
    B <--> P[Scaramouche: partner interactions]
```

## Current boundaries

Much of the event and command logic remains in `bot.py`. A gradual extraction of provider access, transport, memory, and delivery would improve maintainability, but should happen with regression coverage rather than as a cosmetic portfolio rewrite.

The new offline tests exercise the real `anti_repeat.py`: duplicate detection, recent-output bounds, character isolation, and fresh selection. They do not start the bot or call a provider. The separate [repair lab](https://github.com/Kittybri/agent-repair-lab) makes five smaller engineering contracts reproducible without credentials.

## Evidence and limits

The [PDF case study](https://github.com/Kittybri/agent-repair-lab/blob/main/docs/pdf-retrieval.md) explains a failure where Wanderer could retrieve material and Scaramouche could not. The [routing case study](https://github.com/Kittybri/agent-repair-lab/blob/main/docs/turn-ownership.md) documents a coordination design and its limitations. Neither establishes overall model quality or exactly-once delivery.

Provider failure, Discord reconnects, speaker attribution, memory correctness, and complete output need distinct tests. No measured performance experiment is included in this portfolio. Use synthetic demonstrations, and keep private conversations, recordings, documents, credentials, and memory databases out of source control. See [PRIVACY.md](../PRIVACY.md).
