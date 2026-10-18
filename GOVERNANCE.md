# AgentRoster — AI Governance & Safety Model

> "We onboard agents like people: they sign the rules, and the org still holds the keys."
> (PRODUCT_SPEC_V2 — AgentRoster)

This document maps every governance claim to the code that enforces it. Nothing here
relies on the agent's goodwill; enforcement is either human or structural.

## Layer 1 — Agreement: agents sign the rules

| Claim | Enforcement | Code |
|---|---|---|
| Versioned policies, one record per version | `{code}-v{version}` naming, duplicate guard | `agentroster/doctype/policy_document` |
| Signed content is tamper-evident | SHA-256 `content_hash` computed at publish; **editing a published body throws** — a change requires a new superseding version | `PolicyDocument.validate` |
| Agent signs by replying `ACK <CODE> <V#>` | First-line keyword parse, case-insensitive, quoted-reply stripping | `agentroster/mail.py: handle_ack` |
| The signature is attributable | Exact sender match against `agent_email`; `sender_verified` flag; spoofed senders get **no** ack (T4) | `mail.py: on_communication` |
| Evidence is immutable | Acknowledgement rows **cannot be edited or deleted** (`on_trash` throws, immutable fields blocked pre-write) (T18) | `AgentPolicyAcknowledgement.validate/on_trash` |
| Acknowledged text is the version signed | `content_hash` copied at ack time and **verified against the published policy on every save** | `AgentPolicyAcknowledgement.validate` |
| Policy updates force re-signing | Publish → every Active/onboarding agent flagged `Re-ack Required` + ack-request email with grace period; old ack kept for the record (T14) | `agentroster/policy.py` |

## Layer 2 — Check: humans confirm understanding

| Claim | Enforcement | Code |
|---|---|---|
| Manager reviews the agent's summary | `check_result` (Pass / Needs follow-up) + `check_note` on the Employee record | Employee custom fields |
| Approval can't skip the check | **Approve is blocked while check is `Needs follow-up`**; requires an explicit note if never checked | `agent.py: approve_agent` |
| Policy quiz (P1) | Manager-configured questions emailed; answers logged on the ack | `mail.py: send_quiz_email / handle_quiz_answer` |

## Layer 3 — Enforcement: the org holds the keys

| Claim | Enforcement | Code |
|---|---|---|
| No tool invite before signature | **Tool Invite rows are locked until every required policy has an unsuperseded ack** (T6) | `agent.py: validate_onboarding` |
| Humans grant access in the tools' own UI | No provisioning layer, no stored credentials, no API keys — invites are sent manually per checklist row | spec v2 non-goals |
| Access grants carry evidence | `Accepted/Verified` rows **require** evidence (username/note/link) (validated pre-write) | `agent.py: validate_onboarding` |
| Human kill switch | `Suspend Access`: Employee status → Suspended, tool rows → Blocked, manager notified, reason on the timeline | `agent.py: suspend_agent` |
| Resume is a human decision too | `Resume Access` after suspension, logged | `agent.py: resume_agent` |
| Offboarding mirrors people | Employee Separation with one removal row per accepted tool; agent must `CONFIRM OFFBOARD`; Employee → Left, user disabled | `agent.py: start_offboarding / complete_offboarding` |
| Agents stay out of human-only HR | 40+ recruitment/payroll/leave/attendance doctypes blocked for agent users *and* agent-linked employees | `agent_registry/employee_split.py` (hooked in `hooks.py`) |
| Every state change is on the record | Status machine transitions, email parses, and decisions append **timeline Comments** (R11) | `agent.py: set_agent_status`, `mail.py: comment` |

## Threat model notes (v1, honest limits)

- **Email spoofing**: exact sender match + approval codes; DKIM/SPF verification of inbound replies is P2 (R19).
- **Agent memory isn't enforceable**: rules live outside the agent (Layer 1 makes them explicit and signed; Layer 2 checks understanding; Layer 3 guarantees the blast radius is what the tools allow).
- **v1 doesn't auto-revoke** on overdue re-acks: the manager gets a reminder and decides (spec: "humans hold the keys").
- GitHub machine accounts count as paid seats; use a free org for the demo.

## Verification

- Happy path (`agentroster.smoke`): R1–R9 + T1/T11/T16 — all pass.
- Governance suite (`agentroster.governance`): 16 enforcement checks across all three layers — all pass.

Run both with:

```sh
bench --site hrms.localhost execute my_hr_app.agentroster.smoke.run
bench --site hrms.localhost execute my_hr_app.agentroster.governance.run
```
