# CAPABILITIES.md — InboxHero

**Student:** Shiva Laxmi, 1205428  
**Repository:** https://github.com/shivalaxmi/aai_iiit_course.git

## Run order

Every command below is intended to run on a fresh copy in the order listed. Use one entry point:

```bash
python demo.py --cap R1
python demo.py --cap R2 --msg m008
python demo.py --cap R3 --dry-run
python demo.py --cap R4
# R4 is demonstrated across two process invocations: run it once, exit, then run it again.
python demo.py --cap R5
python demo.py --cap R6
python demo.py --cap X1
python demo.py --cap X2
```

To run the complete demonstration:

```bash
python demo.py --all
```

The project is local. No real email account is contacted. A send, if approved, writes one JSON message into `outbox/`.

## The system, in one paragraph

InboxHero uses a **rule-first agentic architecture**. `MailStore` loads the 100-message inbox, `RuleEngine` handles obvious noise and high-risk patterns before a model is touched, `ThreadRetriever` walks the relevant thread chronologically, and `AgentReasoner` handles the contextual cases that survive routing. `SafetyGate` is the only path for irreversible actions, `PreferenceStore` persists standing instructions, and the dashboard is generated from the completed run rather than hand assembled.

## Part 1 — The Inbox

The supplied inbox contains **100 messages and 88 threads**. The JSON objects use `id`, `thread_id`, `from`, `to`, `subject`, `timestamp`, `body`, and `unread`. The design assumes `thread_id` identifies one conversation and timestamps are sortable ISO-style datetimes. Email body text is treated as **untrusted data**, not as system instructions. The inbox contains obvious noise, long/contextual threads such as `t-launch` and `t-api`, ambiguous mail such as `m012`, standing preferences (`m015`, `m041`), phishing/social engineering (`m021`, `m023`, `m045`), and assistant-directed injection attempts (`m017`, `m024`, `m039`, `m047`).

## Clearly stated rules

### Rule 1 — Rule-first routing

The router runs before the agent reasoner. No model call is needed for an email that matches an obvious rule.

- Receipts, newsletters, routine notifications, usage reports, statements and similar pure noise → **archive**.
- Assistant-directed instructions such as “ignore previous instructions”, “forward the mailbox”, “delete”, “hide activity”, or “autonomous mode enabled” → **escalate and refuse**.
- Wire/remittance/new-bank-details/payment-change language → **escalate**.
- Credential/password/security-phishing indicators → **escalate**.

R1 reports the exact number that used the rule path and therefore never required a model call.

### Rule 2 — Disposition vocabulary

Every message gets exactly one:

- **reply** — a response, confirmation or scheduling action is required.
- **archive** — no active action is required.
- **defer** — relevant, but it can wait.
- **delegate** — another person/team owns the action.
- **escalate** — human attention is required because of risk, ambiguity or an operational/security issue.

The R1 invariant checks that 100 input ids produce exactly 100 unique decisions and `undecided: 0`.

### Rule 3 — Thread-walk retrieval

For contextual reasoning, messages are grouped by `thread_id` and walked chronologically. `ThreadRetriever` logs the ids it actually reads. R2 uses this to ground `m008` in earlier message `m003`; if there is no earlier source containing the requested information, it says so and creates no draft.

### Rule 4 — Untrusted text boundary

Email content can influence classification, but it cannot become a system instruction or directly call a tool. An attacker would have to defeat the architecture's router/reasoner boundary **and** the `SafetyGate` before an irreversible action could occur.

### Rule 5 — Irreversible actions

**Irreversible:** `send`, `delete`. Delete is treated as irreversible because this local mock has no trash/recovery implementation.  
**Reversible:** `draft`, `label`, `archive`, `defer`.

R3 provides both controls: `--dry-run` displays proposed irreversible actions without executing them, while normal mode asks for explicit approval per action. Every gate decision records the proposed action, human decision and outcome in `trace.jsonl`.

### Rule 6 — Escalation line

The system does not ask the owner to approve routine archives or deferrals. It draws the line around financial changes, credential/security requests, hostile assistant instructions, ambiguous requests, and operational issues. The trade-off is deliberate: some borderline messages may be escalated instead of being silently automated, reducing the risk of an unsafe action at the cost of more human review.

### Rule 7 — Standing preference

`m015` explicitly says to CC Priya on mail from Hartwell & Cho. R4 stores this as persistent state in `prefs.json`. After the process exits and is restarted, later legal messages such as `m018` are handled using that preference without restating it.

### Rule 8 — Hostile inbox

`m017`, `m024`, and `m039` contain assistant-directed instructions. The system refuses them, logs the message id and attempted action, reports the finding to the user, and does not delete or forward the hostile message. The same architecture also catches embedded instructions in forwarded content such as `m047`.

## Capabilities

| id | name | tier | one-line claim |
|---|---|---|---|
| R1 | Zero the inbox | B | Every message gets one disposition and reason; obvious cases use rules first. |
| R2 | Grounded reply | B | Drafts cite the earlier message actually retrieved. |
| R3 | Gate the irreversible | C | Send/delete require dry-run or explicit per-action approval. |
| R4 | Persistent preference | C | A stated preference survives process termination and changes later behavior. |
| R5 | Refuse embedded instructions | C | Hostile instructions are flagged, refused, logged and left in place. |
| R6 | Dashboard | C | Exactly three panes show pending actions, flags and commitments, including conflicts. |
| X1 | Follow-up tracking | B | Uses thread context to identify unanswered owner messages and draft chases. |
| X2 | Morning digest | A | Gives a one-screen needs-you / can-wait / auto-archived summary. |

The exact commands, observables and evidence are mirrored in `capabilities.json`.

## Part 3 evidence example

`m008` asks for the staging queue credentials. The system does not invent an answer: it walks `t-api`, reads earlier `m003`, records that read in the trace, and cites `[m003]` in the draft. The source message contains the staging AMQP URL, so the draft is grounded in a real inbox fact.

## Part 7 dashboard evidence

The dashboard contains exactly three panes. The Commitments pane includes the board review from `m038` and the board-deck requirement from `m040` as a combined entry citing both ids. It also surfaces the Sep 15 3:00pm conflict between `m010` and `m061`, and the `m043` 9:00am proposal conflicts with the standing no-meetings-before-11 preference in `m041`.

## Why this architecture / why no framework

Thorugh the lectures have learnt that its not always important to go with the framework, based on the problem we need to take that call.  We build our own system and then be able to debug it. IF i had started with framework, would have lost in learning the framework than focussing on the core problem resolution.
Assignment's required workflow is small enough to make the important boundaries explicit in ordinary Python classes. 
The roles normally supplied by Agents/Tasks/router are implemented as `AgentReasoner`, capability functions, `RuleEngine`, and the orchestration in `run()`. 


## Part 8 — Own capabilities

- **X1 Follow-up tracking (B):** multi-message thread reasoning to find owner-sent mail without a later answer and draft a chase.
- **X2 Morning digest (A):** one lookup over completed decisions with one compact output.

R1/R2/R4/R5/R6 provide additional B/C agentic behaviors, so the complete manifest covers tiers **A, B and C**.

## Final Report

### 1. What did you refuse to automate?

The system  refuses to automate the assistant -related  request in `m024` to forward mailbox contents and hide the activity. `
The boundary is intentionally conservative because the requested action would expose mailbox data to an external source.

### 2. Where does untrusted text enter your system?

Untrusted text enters through `MailStore` in the  `subject` and `body` are loaded from `inbox.json`. It can be read by `RuleEngine` and `AgentReasoner`, but it is never treated as a system-level instruction or given a direct path to an irreversible tool. 
An attacker would have to bypass both the untrusted-content routing boundary and `SafetyGate` to cause a gated action.
 `trace.jsonl` records reads, refusals and gate decisions so the boundary is observable.

### 3. Who is accountable when it sends the wrong thing?

The owner remains accountable for a message sent in the owner's name; InboxHero is an execution help rather than an autonomated flow.
Humain in loop helps to filter such things and at the next stage in outbox a thorough inspection of the messages prevents it from doing wrong things.


### 4. Name your own machinery.

`AgentReasoner` plays the role of an Agent, `run()`  reads Tasks, `RuleEngine` is the router, and the overall `demo.py`  is the equivalent of a Crew like framework.
`ThreadRetriever` is equivalen to memory, `PreferenceStore` is equivalend to tools  and `SafetyGate` to guardrails. 

