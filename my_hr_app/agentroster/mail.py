"""Email engine: outbound template sends + inbound reply parser.

Spec: PRODUCT_SPEC_V2 (AgentRoster) - sections 7 and 12.1/12.3.
Subject tag: [AR-<employee id>]. Reply keywords are on the first line, case-insensitive.
"""

import re

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from my_hr_app.agentroster.agent import (
	acks_exist,
	is_agent,
	mark_row_accepted,
	mark_row_blocked,
	set_agent_status,
)
from my_hr_app.agentroster.doctype.agent_policy_acknowledgement.agent_policy_acknowledgement import (
	create_acknowledgement,
)

SUBJECT_TAG = "[AR-{0}]"

# first-line keywords
ACK_RE = re.compile(r"^ACK\b", re.IGNORECASE)
JOINED_RE = re.compile(r"^JOINED\s+(\S+)\s+(\S+)", re.IGNORECASE)
JOINED_TOOL_ONLY_RE = re.compile(r"^JOINED\s+(\S+)$", re.IGNORECASE)
BLOCKED_RE = re.compile(r"^BLOCKED\s+(\S+)\s*(.*)", re.IGNORECASE)
DONE_RE = re.compile(r"^DONE\b", re.IGNORECASE)
CONFIRM_OFFBOARD_RE = re.compile(r"^CONFIRM\s+OFFBOARD\b", re.IGNORECASE)
APPROVE_RE = re.compile(r"^APPROVE\s+(\S+)\s*(.*)", re.IGNORECASE)
CHANGES_RE = re.compile(r"^CHANGES\s+(\S+)\s*(.*)", re.IGNORECASE)

QUIZ_RE = re.compile(r"^ANSWER\s+(\S+)\s*(.*)", re.IGNORECASE)


# ---------------------------------------------------------------- outbound


def subject_for(emp) -> str:
	return SUBJECT_TAG.format(emp.name)


def _context(emp, extra=None):
	ctx = {
		"doc": emp,
		"company": frappe.db.get_value("Company", emp.company, "company_name")
		if emp.company
		else "",
		"manager_name": frappe.db.get_value("Employee", emp.reports_to, "employee_name")
		if emp.reports_to
		else "your manager",
		"operator_name": emp.operator_name or "",
		"profile_url": get_url(f"/app/employee/{emp.name}"),
		"onboarding_url": get_url("/agent-onboarding"),
	}
	if extra:
		ctx.update(extra)
	return ctx


def get_manager_email(emp) -> str | None:
	"""The inviting manager's email (reports_to Employee -> its User)."""
	if not getattr(emp, "reports_to", None):
		return None
	return (
		frappe.db.get_value("Employee", emp.reports_to, "user_id")
		or frappe.db.get_value("Employee", emp.reports_to, "company_email")
		or None
	)


def _send(emp, template_name: str, recipients: list, cc=None, extra_ctx=None, now=False):
	template = frappe.get_doc("Email Template", template_name)
	ctx = _context(emp, extra_ctx)
	message = frappe.render_template(template.response_html or template.response, ctx)
	subject = frappe.render_template(template.subject, ctx)
	try:
		frappe.sendmail(
			recipients=recipients,
			cc=cc or [],
			subject=subject,
			message=message,
			reference_doctype="Employee",
			reference_name=emp.name,
			now=now,
		)
	except Exception as e:
		# an email failure must never block the state machine; it is retried by the queue
		frappe.log_error(title="agentroster outbound", message=f"{template_name}: {e}")


def send_welcome_email(emp):
	"""7.1 Welcome + policies, listing every required published Policy Document."""
	policies = []
	for p in agentroster_required_policies(emp.name):
		policies.append(
			{
				"code": p.code,
				"version": p.version,
				"title": p.title,
				"url": get_url(f"/app/policy-document/{p.name}"),
			}
		)
	recipients = [emp.agent_email]
	cc = [emp.operator_email] if emp.operator_email else []
	ack_url = get_url(f"/agent-ack?t={emp.get('ack_web_token') or ''}")
	_send(
		emp,
		"AgentRoster: Welcome + policies",
		recipients,
		cc=cc,
		extra_ctx={"policies": policies, "ack_url": ack_url, "tool_steps": tool_steps(emp.name)},
	)
	comment(
		emp,
		_("Welcome + policies email sent to {0} (CC operator)").format(", ".join(recipients)),
	)


def agentroster_required_policies(employee: str) -> list:
	from my_hr_app.agentroster.agent import required_policies

	return required_policies(employee)


def send_ack_request(emp, policy, due_date=None):
	"""7.2 Ack request: re-acknowledgement after a policy update."""
	extra = {
		"policy": {
			"code": policy.code,
			"title": policy.title,
			"version": policy.version,
			"effective_date": policy.effective_date,
			"change_summary": policy.change_summary or "",
			"url": get_url(f"/app/policy-document/{policy.name}"),
		},
		"due_date": due_date,
	}
	recipients = [emp.agent_email]
	cc = [emp.operator_email] if emp.operator_email else []
	_send(emp, "AgentRoster: Ack request", recipients, cc=cc, extra_ctx=extra)
	comment(emp, _("Ack request sent for {0} v{1}").format(policy.code, policy.version))


def send_tool_invite_notice(emp, row):
	"""7.3 Tool invite notice, sent when the manager marks the tool invite as sent."""
	tool = frappe.get_doc("Agent Tool", row.agent_tool) if row.get("agent_tool") else None
	extra = {
		"row": {
			"tool": tool.tool_name if tool else row.activity_name,
			"tool_code": tool.tool_code if tool else "",
			"scope": row.get("tool_scope") or "",
			"role": row.get("tool_role") or "",
			"step": row.get("activity_name") or "",
			"description": _plain(row.get("description")),
			"credentials_ready": False,
		},
		"inviter_name": inviter_name(emp),
	}
	from my_hr_app.agentroster import credentials

	if tool and credentials.has_active_credential(emp, tool.name):
		extra["row"]["credentials_ready"] = True
		extra["credentials_endpoint"] = credentials.endpoint_url()
	_send(emp, "AgentRoster: Tool invite notice", [emp.agent_email], extra_ctx=extra)
	comment(
		emp,
		_("Tool invite notice for {0} sent to {1} (invite from {2})").format(
			extra["row"]["tool"], emp.agent_email, extra["inviter_name"]
		),
	)


def inviter_name(emp) -> str:
	"""Tool invites come from the agent's manager; fall back to whoever clicked."""
	if emp.get("reports_to"):
		name = frappe.db.get_value("Employee", emp.reports_to, "employee_name")
		if name:
			return name
	return frappe.utils.get_fullname(frappe.session.user)


def _plain(html) -> str:
	html = (html or "").replace("</p>", "</p> ").replace("<br>", " ")
	return " ".join(frappe.utils.strip_html(html).split())


def tool_steps(employee: str) -> list[dict]:
	"""Tool invite rows on the agent's onboarding, in checklist order, for the emails."""
	from my_hr_app.agentroster.agent import _get_active_onboarding

	onboarding = _get_active_onboarding(employee)
	if not onboarding:
		return []
	rows = frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": onboarding, "parenttype": "Employee Onboarding", "activity_kind": "Tool Invite"},
		fields=["activity_name", "agent_tool", "description"],
		order_by="idx asc",
	)
	return [
		{"tool": r.agent_tool or r.activity_name, "step": r.activity_name, "description": _plain(r.description)}
		for r in rows
	]


def send_first_assignment_email(emp, task, acceptance=None):
	"""7.4 First assignment."""
	extra = {
		"task": {
			"subject": task.subject,
			"description": task.description or "",
			"acceptance": acceptance or "",
		},
		"joined_tools": joined_tools(emp.name),
	}
	_send(emp, "AgentRoster: First assignment", [emp.agent_email], extra_ctx=extra)
	comment(emp, _("First assignment sent: {0}").format(task.subject))


def send_approval_request(emp):
	"""7.5 Approval request to the manager."""
	if not emp.approval_code:
		emp.approval_code = frappe.utils.random_string(6).upper()
		emp.db_set("approval_code", emp.approval_code)
	acks = frappe.get_all(
		"Agent Policy Acknowledgement",
		filters={"employee": emp.name, "superseded": 0},
		fields=["policy_code", "policy_version", "received_at"],
	)
	tools = _onboarding_rows(emp.name, activity_kind="Tool Invite")
	task = frappe.get_doc("Task", emp.first_assignment) if emp.first_assignment else None
	profile_url = get_url(f"/app/employee/{emp.name}")
	extra = {
		"acks": [
			{
				"code": a.policy_code,
				"version": a.policy_version,
				"received_at": a.received_at,
				"late": False,
			}
			for a in acks
		],
		"tools": [{"tool": t.evidence or "", "status": t.access_status} for t in tools],
		"task": {
			"subject": task.subject if task else "",
			"submitted_at": now_datetime(),
			"links": (task.description or "") if task else "",
		},
		"profile_url": profile_url,
		"approval_code": emp.approval_code,
	}
	_send(emp, "AgentRoster: Approval request", [get_manager_email(emp) or emp.agent_email], extra_ctx=extra)
	comment(emp, _("Approval request sent to the manager"))


def send_offboarding_notice(emp, reason, last_day):
	"""7.6 Offboarding notice."""
	tools = joined_tools(emp.name)
	recipients = [emp.agent_email]
	cc = [emp.operator_email] if emp.operator_email else []
	_send(
		emp,
		"AgentRoster: Offboarding notice",
		recipients,
		cc=cc,
		extra_ctx={"reason": reason or "", "last_day": last_day, "tools": tools},
	)
	comment(emp, _("Offboarding notice sent to {0}").format(", ".join(recipients)))


def send_active_email(emp, approved_via, note):
	extra = {"approved_via": approved_via, "note": note or ""}
	_send(emp, "AgentRoster: You are active", [emp.agent_email], extra_ctx=extra)
	comment(emp, _("Approved to Active via {0}").format(approved_via))


def send_changes_requested_email(emp, note):
	extra = {"note": note or ""}
	_send(emp, "AgentRoster: Changes requested", [emp.agent_email], extra_ctx=extra)
	comment(emp, _("Manager requested changes: {0}").format(note))


def send_quiz_email(emp, ack, policy):
	extra = {
		"ack": {"policy_code": ack.policy_code, "name": ack.name},
		"questions": [q.as_dict() for q in policy.quiz_questions],
	}
	_send(emp, "AgentRoster: Policy quiz", [emp.agent_email], extra_ctx=extra)


def send_manager_notification(emp, text):
	"""Smaller automatic emails to the manager."""
	recipients = [get_manager_email(emp)] if get_manager_email(emp) else []
	if recipients:
		try:
			frappe.sendmail(
				recipients=recipients,
				subject=subject_for(emp) + " " + text,
				message=f"<p>{text}</p><p><a href=\"{get_url('/app/employee/' + emp.name)}\">Open {emp.employee_name}</a></p>",
				reference_doctype="Employee",
				reference_name=emp.name,
				now=True,
			)
		except Exception as e:
			frappe.log_error(title="agentroster outbound", message=f"manager notification: {e}")


def _onboarding_rows(employee: str, **filters):
	from my_hr_app.agentroster.agent import _get_active_onboarding

	onboarding = _get_active_onboarding(employee)
	if not onboarding:
		return []
	return frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": onboarding, "parenttype": "Employee Onboarding", **filters},
		fields=["agent_tool", "access_status", "evidence"],
	)


def joined_tools(employee: str) -> list[str]:
	rows = _onboarding_rows(employee, access_status=["in", ["Accepted", "Verified"]])
	return [r.agent_tool for r in rows]


def comment(emp, text: str):
	"""Every state change and parsed email lands on the Employee timeline (R11)."""
	try:
		emp.add_comment("Comment", text)
	except Exception:
		frappe.log_error(title="agentroster", message=f"comment failed: {text}")


# ---------------------------------------------------------------- inbound


def find_employee_by_subject_tag(subject: str | None):
	match = re.search(r"\[AR-([^\]]+)\]", subject or "")
	if not match:
		return None
	name = match.group(1)
	if frappe.db.exists("Employee", name):
		return name
	return None


def find_employee_by_sender(sender: str):
	if not sender:
		return None
	return frappe.db.get_value(
		"Employee", {"worker_type": "Agent", "agent_email": sender}, "name"
	)


def first_line(text: str | None) -> str:
	for raw in (text or "").splitlines():
		line = raw.strip()
		if line and not line.startswith(">") and not line.lower().startswith("from:"):
			return line
	return ""


def is_manager(sender: str, emp=None) -> bool:
	if not sender:
		return False
	manager_email = get_manager_email(emp)
	if manager_email and sender.lower() == manager_email.lower():
		return True
	# any employee who has an agent reporting to them
	emp_name = frappe.db.get_value("Employee", {"company_email": sender}, "name")
	if not emp_name:
		emp_name = frappe.db.get_value("Employee", {"user_id": frappe.db.get_value("User", {"email": sender}, "name")}, "name")
	if not emp_name:
		return False
	return bool(frappe.db.exists("Employee", {"reports_to": emp_name, "worker_type": "Agent"}))


def on_communication(doc, method=None):
	"""Communication.after_insert hook: parse inbound replies (spec 12.3)."""
	if doc.sent_or_received != "Received":
		return
	if doc.communication_medium != "Email":
		return

	sender = (doc.sender or "").strip()
	employee = doc.reference_doctype == "Employee" and doc.reference_name or None
	if not employee:
		employee = find_employee_by_subject_tag(doc.subject)
	if not employee:
		employee = find_employee_by_sender(sender)
	if not employee:
		return

	emp = frappe.get_doc("Employee", employee)
	if not is_agent(emp):
		return

	line = first_line(doc.text_content or doc.content or "")
	if not line:
		return

	try:
		handle_reply(doc, emp, sender, line)
	except Exception:
		frappe.db.rollback()
		frappe.log_error("agentroster inbound parse", frappe.get_traceback())
		frappe.db.commit()


def handle_reply(doc, emp, sender: str, line: str):
	sender_is_agent = sender.lower() == (emp.agent_email or "").lower()
	sender_is_manager = is_manager(sender, emp)

	if sender_is_agent:
		if ACK_RE.match(line):
			handle_ack(doc, emp, sender, line)
		elif JOINED_TOOL_ONLY_RE.match(line):
			handle_joined(doc, emp, sender, line)
		elif JOINED_RE.match(line):
			handle_joined(doc, emp, sender, line)
		elif BLOCKED_RE.match(line):
			handle_blocked(doc, emp, sender, line)
		elif DONE_RE.match(line):
			handle_done(doc, emp, sender, line)
		elif CONFIRM_OFFBOARD_RE.match(line):
			handle_confirm_offboard(doc, emp, sender, line)
		elif QUIZ_RE.match(line):
			handle_quiz_answer(doc, emp, sender, line)
		else:
			comment(emp, _("Unverified reply from sender, no state change"))
	elif sender_is_manager:
		if APPROVE_RE.match(line):
			handle_approve(doc, emp, sender, line)
		elif CHANGES_RE.match(line):
			handle_changes(doc, emp, sender, line)
		else:
			comment(emp, _("Unverified reply from sender, no state change"))
	else:
		comment(emp, _("Unverified reply from sender, no state change"))


def handle_ack(doc, emp, sender, line):
	"""ACK <CODE> <V#>[, <CODE> <V#>...] -> one Agent Policy Acknowledgement per policy."""
	body = line[3:].strip()
	items = [item.strip() for item in body.split(",") if item.strip()]
	created = []
	for item in items:
		match = re.match(r"(\S+)\s+v?(\d+)", item)
		if not match:
			continue
		code, version = match.group(1).upper(), int(match.group(2))
		policy = frappe.db.get_value(
			"Policy Document",
			{"code": code, "version": version, "status": "Published"},
			"name",
		)
		if not policy:
			comment(
				emp,
				_("Couldn't parse/validate: no published {0} v{1} (from {2})").format(code, version, sender),
			)
			send_manager_notification(
				emp, _("Couldn't parse reply: no published {0} v{1}").format(code, version)
			)
			continue
		verified = sender.lower() == (emp.agent_email or "").lower()
		ack = create_acknowledgement(
			employee=emp.name,
			policy_document=policy,
			method="Email reply",
			source_email=sender,
			communication=doc.name,
			ack_text=(doc.text_content or "")[:4000],
			received_at=doc.creation,
		)
		frappe.db.set_value("Agent Policy Acknowledgement", ack.name, "sender_verified", verified)
		created.append(f"{code} v{version}")

	if created and acks_exist(emp.name):
		# the acks above update the Employee row (policy_ack_status), so reload before saving
		emp.reload()
		set_agent_status(emp, "Policies Acknowledged", save=True)
		send_manager_notification(emp, _("Policies acknowledged"))
		comment(emp, _("Agent Policy Acknowledgement created: {0}").format(", ".join(created)))


def handle_joined(doc, emp, sender, line):
	match = JOINED_RE.match(line) or JOINED_TOOL_ONLY_RE.match(line)
	if not match:
		return
	tool_code = match.group(1).lower().strip()
	handle = match.group(2) if match.re is JOINED_RE else ""
	if not handle:
		handle = ""
	changed = mark_row_accepted(emp.name, tool_code, handle, communication=doc.name)
	if changed:
		# doc.save() already fired Employee Onboarding.on_update -> status sync
		send_manager_notification(emp, _("Agent joined {0}").format(tool_code))
	else:
		comment(emp, _("Couldn't parse reply: no invited row for {0}").format(tool_code))


def handle_blocked(doc, emp, sender, line):
	match = BLOCKED_RE.match(line)
	tool_code = match.group(1).lower().strip()
	note = match.group(2).strip()
	mark_row_blocked(emp.name, tool_code, note, communication=doc.name)
	send_manager_notification(emp, _("Agent blocked on {0}: {1}").format(tool_code, note))


def handle_done(doc, emp, sender, line):
	"""DONE + links -> Task Completed, status Awaiting Approval, approval email to manager."""
	if not emp.first_assignment:
		comment(emp, _("Couldn't parse reply: no first assignment task"))
		return
	task = frappe.get_doc("Task", emp.first_assignment)
	task.status = "Completed"
	task.flags.from_agentroster = True
	task.save(ignore_permissions=True)
	set_agent_status(emp, "Awaiting Approval", save=True)
	comment(emp, _("First assignment submitted: {0}").format(line[4:].strip()))
	send_approval_request(emp)


def handle_confirm_offboard(doc, emp, sender, line):
	separation = frappe.db.get_value(
		"Employee Separation", {"employee": emp.name, "docstatus": ["!=", 2]}, "name"
	)
	if not separation:
		comment(emp, _("Couldn't parse reply: no active offboarding"))
		return
	frappe.db.set_value("Employee Separation", separation, "agent_confirmation", "Received")
	comment(emp, _("Offboarding confirmed by agent: {0}").format(line[:200]))
	send_manager_notification(emp, _("Offboarding confirmed"))


def handle_quiz_answer(doc, emp, sender, line):
	match = QUIZ_RE.match(line)
	if not match:
		return
	ack_name = match.group(1)
	if frappe.db.exists("Agent Policy Acknowledgement", ack_name):
		frappe.db.set_value("Agent Policy Acknowledgement", ack_name, "quiz_answers", line[:2000])


def handle_approve(doc, emp, sender, line):
	match = APPROVE_RE.match(line)
	code = match.group(1)
	note = match.group(2).strip()
	if code.upper() != (emp.approval_code or "").upper():
		comment(emp, _("Couldn't parse reply: wrong approval code (from {0})").format(sender))
		return
	emp.approved_by = frappe.session.user or "Administrator"
	emp.approved_on = now_datetime()
	emp.approval_note = note
	set_agent_status(emp, "Active", save=True)
	for onboarding in frappe.get_all(
		"Employee Onboarding", filters={"employee": emp.name, "docstatus": 1}, pluck="name"
	):
		frappe.db.set_value("Employee Onboarding", onboarding, "boarding_status", "Completed")
	comment(emp, _("Approved via email from {0}").format(sender))
	send_active_email(emp, "APPROVE email", note)


def handle_changes(doc, emp, sender, line):
	match = CHANGES_RE.match(line)
	code = match.group(1)
	note = match.group(2).strip()
	if code.upper() != (emp.approval_code or "").upper():
		comment(emp, _("Couldn't parse reply: wrong approval code (from {0})").format(sender))
		return
	set_agent_status(emp, "First Assignment", save=True)
	comment(emp, _("Manager requested changes from {0}: {1}").format(sender, note))
	send_changes_requested_email(emp, note)
