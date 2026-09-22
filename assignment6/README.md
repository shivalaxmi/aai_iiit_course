#https://github.com/shivalaxmi/#aai_iiit_course
# InboxHero — Assignment 06

**Student:** Shiva Laxmi  
**Roll Number:** 1205428  
**Repository:** `https://github.com/shivalaxmi/aai_iiit_course`

InboxHero is a local-only rule-first agentic inbox manager for the supplied 100-message `inbox.json`. See `CAPABILITIES.md` for the graded capability manifest and `capabilities.json` for its machine-readable form.

## Quick start

```bash
python demo.py --cap R1
python demo.py --cap R2 --msg m008
python demo.py --cap R3 --dry-run
python demo.py --cap R4
python demo.py --cap R4
python demo.py --cap R5
python demo.py --cap R6
python demo.py --cap X1
python demo.py --cap X2
```

For R4, the first run creates `prefs.json`; the second run demonstrates behavior after the first process has exited.

## Architecture

`MailStore -> RuleEngine -> AgentReasoner -> SafetyGate`, with `ThreadRetriever`, `PreferenceStore`, `EventLog`, and Dashboard generation around the workflow. Rules handle obvious noise and high-risk indicators before the optional Ollama model is considered. Contextual messages use chronological thread-walk retrieval. Email is untrusted data and cannot directly invoke irreversible actions.

## Configuration

The local model is configured through environment variables in `config.py`:

```text
MODEL_PROVIDER=ollama
MODEL_NAME=gemma3:4b
OLLAMA_HOST=http://localhost:11434
```

No `.env` file or credentials are included.

## Outputs

- `decisions.json` — Part 2 dispositions
- `trace.jsonl` — reads, decisions, model calls, refusals and gates
- `prefs.json` — persistent preference state
- `dashboard.json` / `dashboard.html` — Part 7 dashboard
- `outbox/` — only approved local sends

## Final Report

The four required answers are in `CAPABILITIES.md` so the human-readable manifest contains the assignment's requested justifications and evidence.
