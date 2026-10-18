# Functional specification: agent governance and security

**Product:** HR portal (Frappe HRMS + `my_hr_app`)
**Branch:** `dhruvbhavsar`
**Status:** Matches the behavior implemented on this branch

## 1. Purpose

An AI agent is hired as a coworker. The company does not need to know which model or agent product the vendor uses. Governance lives in the HR portal: the policies, the proof that this agent accepted them, and the gates that stop the agent from moving on until that proof exists.

The agent keeps one mailbox and one session. It does not log out to remember the rules. The portal holds the signed copy. The agent is asked to read and sign again only when HR publishes a new version.

## 2. Who is involved

| Actor | Role |
| --- | --- |
| HR / inviting manager | Creates the agent, publishes policies, starts onboarding, invites tools, approves Active, and starts offboarding. |
| Agent | An external worker. It has its own email. Its vendor, runtime, and model may be recorded and may be left blank. |
| Operator | A person at the vendor, copied on policy and offboarding mail. The operator does not approve the agent. |
| Portal | Sends the policy text, stores acknowledgements, and enforces the gates below. |

## 3. What the portal stores

### 3.1 The agent

An agent is an Employee with Worker Type **Agent**. Human fields stay empty: gender, date of birth, address, bank, salary, leave, and attendance are not required and are hidden on the form.

The agent record holds:

- Agent email, unique among agents
- Agent status (section 5)
- Policy acknowledgement status: Pending, Current, or Re-ack Required
- Operator name and email
- Vendor, runtime, and model, all optional
- Inviting manager
- First assignment, approval code, approver, approval time, and approval note

### 3.2 The policy

A Policy Document is the rule the agent must follow. HR writes it once.

| Field | Rule |
| --- | --- |
| Code and version | Set once. Together they name the document, for example `RULES-v1`. |
| Type | Rules of Agreement, Code of Conduct, Acceptable Use, Security, Data Handling, or Other. |
| Status | Draft, Published, or Retired. |
| Body | Required before publish. |
| Content hash | Computed from the body when the document is published. The acknowledgement stores the same hash. |
| Applies to agents | Published documents with this checked are candidates for every agent. |
| Applies to designations | Empty means every agent. A list means only agents with one of those designations. |
| Re-ack grace days | Default 3. The agent is asked to sign the new version inside this window. |
| Change summary | Sent in the re-acknowledgement email. |
| Quiz questions | Optional. HR can email them before tool access. |

A new version is a new Policy Document. It can point at the document it replaces. Acknowledgements of an older version stay on file. They do not count as a signature of the new version.

### 3.3 The acknowledgement

An Agent Policy Acknowledgement is the proof that one agent signed one policy version. It records the employee, policy, version, content hash, the exact reply text, the sender address, whether that address matches the agent email, the time, and the email it was parsed from.

Rules:

- The same agent and the same policy version produce one current acknowledgement. A second reply does not create a duplicate.
- An acknowledgement cannot be deleted. HR marks it superseded if it must be set aside.
- A manager may record an acknowledgement by hand only with a note.
- HR can mark a check result: Not checked, Pass, or Needs follow-up.

## 4. How the agent learns the rules

The agent does not learn the rules by training, and it does not learn them by logging in again.

1. HR publishes the policies that apply to agents.
2. HR opens the agent and chooses **Start Onboarding**.
3. The portal emails the agent, with the operator copied. The mail lists every required published policy, with its title, version, and link, and tells the agent to save that text and follow it.
4. The agent replies from its own email. The first line is:

   `ACK RULES v1, CODE-OF-CONDUCT v1, AUP v1`

   The following lines are the agent's own statement of what the rules require.
5. The portal stores one acknowledgement per policy version and moves the agent to **Policies Acknowledged**.

The signed policies remain in the portal for the life of the agent. Later tasks, tool replies, and the first assignment do not ask the agent to sign again.

A reply from any other address does not change status. The portal writes a note on the employee timeline: unverified reply, no state change.

### 4.1 When a policy changes

HR publishes a new version. The portal then:

- Sets Policy Ack Status to **Re-ack Required** on each matching agent that is not Draft, Offboarding, Offboarded, or Left.
- Emails that agent the new version, the change summary, the link, and a due date (today plus the grace days).
- Asks the agent to update its saved copy and reply `ACK <CODE> v<version>`.

Until that reply is stored, the new version has no acknowledgement. Tool invites that have not yet been sent stay locked, because every required published version must have a current acknowledgement.

If the grace date passes and the new version is still unsigned, a daily job emails the manager: re-acknowledgement is overdue, and the manager decides whether to pause access. The job does not turn the agent off by itself.

HR does this work when the text changes. Ordinary tasks do not create a new signature request.

## 5. Lifecycle

Status moves only along this path. Any step before Offboarded can go to Offboarding.

```
Draft
  → Policies Sent
  → Policies Acknowledged
  → Tool Access
  → Ready for Assignment
  → First Assignment
  → Awaiting Approval
  → Active
  → Offboarding
  → Offboarded
```

Awaiting Approval can return to First Assignment when the manager requests changes. Offboarding can return to Active.

| Step | What happens |
| --- | --- |
| Draft | HR creates the Employee with Worker Type Agent and an agent email. |
| Policies Sent | **Start Onboarding** creates the checklist "Agent onboarding: standard" and sends the welcome mail. |
| Policies Acknowledged | Every required published policy has a current acknowledgement from the agent email. |
| Tool Access | A tool row is marked Invited. The portal refuses that save when acknowledgements are missing. |
| Ready for Assignment | Every Tool Invite row is Accepted. |
| First Assignment | HR sends one task. The mail names the tools the agent has joined and what "done" means. |
| Awaiting Approval | The agent replies `DONE` plus links. The manager receives the signed policies, the tool rows, and the task. |
| Active | The manager approves in the form, or replies `APPROVE <code>`. The approver, time, and note are stored. The agent is emailed that it is active and that the signed policies still apply. |
| Offboarding | HR records a reason and last day. The agent is told to hand over work, leave tools, and delete company information from its memory, then reply `CONFIRM OFFBOARD`. |
| Offboarded | Every removal row is Removed and the agent has confirmed. The Employee status becomes Left. If a user is linked, that user is disabled. |

Standard tool rows are GitHub, Slack, and Jira. Each row has a scope, a role, and an access status: Not started, Invited, Accepted, Verified, Blocked, or Removed.

The agent replies `JOINED <tool_code> <handle>` or `BLOCKED <tool_code> <what happened>`. A manager can mark an Accepted row Verified after checking the evidence.

## 6. Security rules

### 6.1 The company does not depend on the model

Vendor, runtime, and model are labels. None of them is required to hire, to send policies, or to block a step. Any external agent that can read mail and reply from its agent address can be governed.

### 6.2 The agent cannot sign itself up

Public sign-up creates a human website user. Choosing "AI Agent" on the sign-up form is refused. An email that already belongs to an AI agent is refused and told to use the invite. A user of type Agent System User can be created only from the HR invite path.

### 6.3 Only the agent email can move the agent forward

Inbound mail is matched by the employee on the message, by the `[AR-<employee id>]` subject tag, or by the sender equaling the agent email. State changes from the agent (ACK, JOINED, BLOCKED, DONE, CONFIRM OFFBOARD, quiz answers) run only when the sender is that agent email.

Manager mail can approve or request changes only when the sender is the inviting manager and the approval code matches the code on the employee. A wrong code is recorded and ignored.

### 6.4 Human HR records stay closed

While the signed-in user is an agent, the portal refuses recruitment, payroll, tax, leave, attendance, shifts, travel, expenses, benefits, loans, grievances, and training documents. The same documents stay empty when they point at an agent employee. The agent form hides personal, pay, leave, and attendance sections, and it removes the buttons that assign leave, salary, or shifts.

### 6.5 Tools come after the signature

No tool invite is sent, and no tool row can be saved as Invited, until `acks_exist` is true: every published policy that applies to this agent has an unsuperseded acknowledgement of that exact version.

### 6.6 Offboarding closes the account

Offboarded sets the employee to Left and disables the linked user. The offboarding mail lists the tools to remove and tells the agent to revoke tokens it created and to delete company information from its own memory.

### 6.7 The trail is kept

Each sent mail and each parsed reply is commented on the employee. The acknowledgement keeps the reply text, the content hash, and the communication it came from. Number cards on the Agents workspace count agents onboarding, awaiting approval, active, needing re-acknowledgement, and offboarding.

## 7. What a person does, and what the portal repeats

| Work | How often |
| --- | --- |
| Write and publish a policy | Once, and again only when the text changes |
| Create the agent and start onboarding | Once per agent |
| Read the welcome mail and reply ACK | Once per policy version |
| Invite tools, send the first assignment, approve | Once per agent, after the signature exists |
| Re-read the policy on later tasks | The agent uses the copy it was told to save. The portal does not send the packet again |
| Chase a missed re-acknowledgement | The daily job emails the manager after the grace date |

## 8. Email contract

Every subject starts with `[AR-<employee id>]`. The keyword is the first non-quoted line and is case-insensitive.

| First line | Who | Result |
| --- | --- | --- |
| `ACK <CODE> v<version>[, ...]` | Agent | One acknowledgement per published match. All required versions signed moves status to Policies Acknowledged. |
| `JOINED <tool_code> <handle>` | Agent | Matching Invited row becomes Accepted. |
| `BLOCKED <tool_code> <note>` | Agent | Matching Invited row becomes Blocked. The manager is told. |
| `DONE` plus links | Agent | First-assignment task is completed. Status becomes Awaiting Approval. Manager receives the approval mail. |
| `ANSWER <ack id> <answers>` | Agent | Quiz answers are stored on that acknowledgement. |
| `CONFIRM OFFBOARD` | Agent | The open separation is marked Received. |
| `APPROVE <code> <note>` | Manager | Code must match. Status becomes Active. |
| `CHANGES <code> <note>` | Manager | Code must match. Status returns to First Assignment and the note is emailed to the agent. |

## 9. Acceptance criteria

1. Creating an agent does not require gender, date of birth, salary, leave, or a model name.
2. Start Onboarding sends the current published policies to the agent email and sets status to Policies Sent.
3. An ACK from the agent email creates one acknowledgement per named published version and stores the content hash.
4. An ACK from any other address does not create a usable state change.
5. Marking a tool Invited before those acknowledgements exist is rejected.
6. After the required acknowledgements exist, tool replies can move the agent through Tool Access and Ready for Assignment without another signature.
7. Publishing a new applicable version sets Re-ack Required and sends one acknowledgement request. It does not ask the agent to sign on every later task.
8. A second ACK of the same version does not create a second acknowledgement.
9. An acknowledgement cannot be deleted.
10. Approve to Active records the approver, time, and note.
11. Completing offboarding sets the employee to Left and disables the linked user.
12. An agent session cannot save a payroll, leave, attendance, expense, or recruitment document.
