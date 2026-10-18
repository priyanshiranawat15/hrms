"""Agent lifecycle engine: status machine, ack lock, onboarding and approval actions.

Spec: PRODUCT_SPEC_V2 (AgentRoster) - sections 6, 9 and 12.
"""

from collections.abc import Callable

import frappe
from frappe import _
from frappe.utils import now_datetime

from my_hr_app.agentroster.doctype.agent_policy_acknowledgement.agent_policy_acknowledgement import (
	create_acknowledgement,
)

AGENT_STATUS_FIELD = "agent_status"

AGENT_STATUSES = [
	"Draft",
	"Policies Sent",
	"Policies Acknowledged",
	"Tool Access",
	"Ready for Assignment",
	"First Assignment",
	"Awaiting Approval",
	"Active",
	"Offboarding",
	"Offboarded",
]

# Any pre-Active status can be cancelled into Offboarding (spec 9).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
	"Draft": {"Policies Sent", "Offboarding"},
	"Policies Sent": {"Policies Acknowledged", "Offboarding"},
	"Policies Acknowledged": {"Tool Access", "Offboarding"},
	"Tool Access": {"Ready for Assignment", "Offboarding"},
	"Ready for Assignment": {"First Assignment", "Offboarding"},
	"First Assignment": {"Awaiting Approval", "First Assignment", "Offboarding"},
	"Awaiting Approval": {"Active", "First Assignment", "Offboarding"},
	"Active": {"Offboarding"},
	"Offboarding": {"Offboarded", "Active"},
	"Offboarded": set(),
}

ONBOARDING_TEMPLATE = "Agent onboarding: standard"
SEPARATION_TEMPLATE = "Agent separation: standard"


def is_agent(employee) -> bool:
	return (getattr(employee, "worker_type", None) or "Human") == "Agent"


def get_agent_status(employee_name: str) -> str | None:
	return frappe.db.get_value("Employee", employee_name, AGENT_STATUS_FIELD)


def transition_allowed(old: str | None, new: str | None) -> bool:
	if new == old:
		return True
	if not old:
		return new == "Draft"
	return new in ALLOWED_TRANSITIONS.get(old, set())


HUMAN_HR_ROLES = {"System Manager", "HR Manager", "HR User"}


def require_human_manager(emp):
	"""Lifecycle buttons are for humans: HR, or the agent's own manager. Never the agent itself."""
	user = frappe.session.user
	if user == "Administrator":
		return
	if emp.get("user_id") and user == emp.user_id:
		frappe.throw(
			_("An agent can't move its own onboarding or approval. A human manager has to do this."),
			frappe.PermissionError,
		)
	if HUMAN_HR_ROLES & set(frappe.get_roles(user)):
		return
	manager_users = {
		frappe.db.get_value("Employee", e, "user_id")
		for e in (emp.get("reports_to"), emp.get("inviting_manager"))
		if e
	}
	if user in manager_users:
		return
	frappe.throw(_("Only HR or {0}'s manager can do this").format(emp.employee_name), frappe.PermissionError)


def manager_user(emp) -> str | None:
	"""The User of the agent's manager (reports_to, else inviting manager)."""
	for e in (emp.get("reports_to"), emp.get("inviting_manager")):
		if e:
			user = frappe.db.get_value("Employee", e, "user_id")
			if user:
				return user
	return None


TOOL_DONE_STATUSES = ("Accepted", "Verified")


def set_agent_status(doc, status: str, save: bool = False):
	"""Move an agent's status, raising on an illegal transition. Every move is logged to the timeline (R11)."""
	old = get_agent_status(doc.name) if not doc.is_new() else None
	if not transition_allowed(old, status):
		frappe.throw(
			_("Illegal agent status transition: {0} -> {1}").format(old or "(new)", status)
		)
	doc.set(AGENT_STATUS_FIELD, status)
	if save:
		doc.flags.from_agentroster = True
		doc.save(ignore_permissions=True)
		try:
			doc.add_comment(
				"Comment",
				_("Agent status: {0} -> {1} (by {2})").format(
					old or "New", status, frappe.session.user or "system"
				),
			)
		except Exception:
			pass


def validate_agent(doc, method=None):
	"""Employee.validate hook for agents: transitions, ack lock, agent email."""
	validate_transition(doc)
	validate_agent_email(doc)


def validate_transition(doc):
	if not is_agent(doc):
		return
	old = None
	if not doc.is_new():
		old = get_agent_status(doc.name)
	new = doc.get(AGENT_STATUS_FIELD) or "Draft"
	if not doc.is_new() and doc.flags.from_agentroster:
		return
	if not transition_allowed(old, new if old else "Draft" if new == "Draft" else new):
		frappe.throw(
			_("Illegal agent status transition: {0} -> {1}").format(old or "(new)", new)
		)


def validate_agent_email(doc):
	if not is_agent(doc):
		return
	if not doc.agent_email:
		frappe.throw(_("Agent email is required for worker_type 'Agent'"))
	if doc.agent_email and doc.agent_email != (doc.prefered_email or "") and not doc.prefered_email:
		doc.prefered_email = doc.agent_email
	duplicate = frappe.db.exists(
		"Employee",
		{
			"worker_type": "Agent",
			"agent_email": doc.agent_email,
			"name": ["!=", doc.name or ""],
		},
	)
	if duplicate:
		frappe.throw(_("Agent email {0} is already on another agent ({1})").format(doc.agent_email, duplicate))


def required_policies(employee) -> list:
	"""Published Policy Documents that apply to this agent."""
	policies = frappe.get_all(
		"Policy Document",
		filters={"status": "Published", "applies_to_agents": 1},
		fields=["name", "code", "title", "version", "content_hash", "effective_date"],
	)
	designation = frappe.db.get_value("Employee", employee, "designation") or ""
	out = []
	for p in policies:
		applies_to = frappe.get_all(
			"Policy Applies To",
			filters={"parent": p.name, "parenttype": "Policy Document"},
			pluck="designation",
		)
		if not applies_to or (designation and designation in applies_to):
			out.append(p)
	return out


def acks_exist(employee: str) -> bool:
	"""All required published policies have an unsuperseded acknowledgement."""
	for p in required_policies(employee):
		acked = frappe.db.exists(
			"Agent Policy Acknowledgement",
			{
				"employee": employee,
				"policy_code": p.code,
				"policy_version": p.version,
				"superseded": 0,
			},
		)
		if not acked:
			return False
	return True


def validate_onboarding(doc, method=None):
	"""Employee Onboarding validate: tool invite rows are locked until all required acks exist.

	Also syncs the agent status from the checklist rows (spec 6.1 steps 4-5) and
	enforces that Accepted/Verified rows carry evidence (Layer 3 audit).
	"""
	employee = doc.employee
	if not employee or not frappe.db.exists("Employee", employee):
		return
	if not is_agent(frappe.get_doc("Employee", employee)):
		return
	for row in doc.activities:
		if row.get("access_status") == "Invited" and not acks_exist(employee):
			frappe.throw(
				_("Row {0}: policies must be acknowledged before any tool invite is sent").format(
					row.activity_name
				)
			)
		if (row.get("access_status") or "") in ("Accepted", "Verified") and not (row.get("evidence") or "").strip():
			frappe.throw(
				_("Row {0}: evidence (username, note) is required to record Accepted/Verified").format(
					row.activity_name
				)
			)


def on_onboarding_update(doc, method=None):
	"""Sync agent status when checklist rows move (Invited -> Tool Access, all Accepted -> Ready)."""
	if not doc.employee:
		return
	emp = frappe.get_doc("Employee", doc.employee)
	if not is_agent(emp):
		return
	rows = doc.activities or []
	if any(r.get("access_status") == "Invited" for r in rows):
		set_agent_status(emp, "Tool Access", save=True)
	tool_rows = [r for r in rows if (r.get("activity_kind") or "") == "Tool Invite"]
	if tool_rows and all((r.get("access_status") or "") in TOOL_DONE_STATUSES for r in tool_rows):
		set_agent_status(emp, "Ready for Assignment", save=True)


def on_agent_update(doc, method=None):
	"""Employee.on_update hook for agents."""
	if not is_agent(doc):
		return
	if doc.flags.from_agentroster:
		return
	# When the manager starts offboarding from the Employee form, the Employee
	# Separation flow drives the rest (agentroster.agent.start_offboarding).


def get_onboarding_template_name():
	return frappe.db.get_value("Employee Onboarding Template", {"title": ONBOARDING_TEMPLATE}, "name")


def get_separation_template_name():
	return frappe.db.get_value("Employee Separation Template", {"title": SEPARATION_TEMPLATE}, "name")


@frappe.whitelist()
def start_onboarding(employee: str):
	"""Create the Employee Onboarding from the agent template and send the welcome email."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if get_agent_status(employee) != "Draft":
		frappe.throw(_("Onboarding has already started for this agent"))

	onboarding = frappe.new_doc("Employee Onboarding")
	template = frappe.get_doc("Employee Onboarding Template", get_onboarding_template_name())
	onboarding.employee = emp.name
	onboarding.employee_name = emp.employee_name
	onboarding.company = emp.company
	onboarding.designation = emp.designation
	onboarding.department = emp.department
	onboarding.employee_grade = emp.grade
	onboarding.against_employee = emp.reports_to
	onboarding.template = template.name
	onboarding.date_of_joining = emp.date_of_joining or frappe.utils.today()
	onboarding.boarding_begins_on = frappe.utils.today()
	onboarding.notify_users_by_email = 1
	owner_user = manager_user(emp)
	for row in template.activities:
		values = row.as_dict() if hasattr(row, "as_dict") else dict(row)
		# the manager sends the tool invites and approves; HR stays on the other rows
		if owner_user and not values.get("user") and (values.get("activity_kind") or "") in ("Tool Invite", "Approval"):
			values["user"] = owner_user
		onboarding.append("activities", values)
	onboarding.flags.from_agentroster = True
	onboarding.insert(ignore_permissions=True)

	set_agent_status(emp, "Policies Sent", save=True)
	frappe.db.commit()
	# web-form ack fallback (R14/P1): signed link the agent can use if email parsing fails
	if not emp.get("ack_web_token"):
		emp.db_set("ack_web_token", frappe.utils.random_string(24))
	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_welcome_email(emp)
	frappe.msgprint(_("Onboarding started; welcome email queued to {0}").format(emp.agent_email))
	return onboarding.name


@frappe.whitelist()
def send_policy_quiz(employee: str, ack_name: str):
	"""P1: email the manager-configured policy quiz for one acknowledgement."""
	from my_hr_app.agentroster import mail

	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	ack = frappe.get_doc("Agent Policy Acknowledgement", ack_name)
	policy = frappe.get_doc("Policy Document", ack.policy_document)
	if not policy.quiz_questions:
		frappe.throw(_("This policy has no quiz questions configured"))
	mail.send_quiz_email(emp, ack, policy)
	frappe.msgprint(_("Quiz sent to {0}").format(emp.agent_email))


@frappe.whitelist()
def send_tool_invites(employee: str):
	"""Mark every not-started Tool Invite row as Invited (locked until acks) and email the notices."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if not acks_exist(employee):
		frappe.throw(_("Policies must be acknowledged first"))
	onboarding_name = _get_active_onboarding(employee)
	if not onboarding_name:
		frappe.throw(_("No active onboarding for this agent"))
	doc = frappe.get_doc("Employee Onboarding", onboarding_name)
	sent = []
	for row in doc.activities:
		if (row.activity_kind or "") == "Tool Invite" and (row.access_status or "Not started") == "Not started":
			row.access_status = "Invited"
			sent.append(row)
	doc.flags.from_agentroster = True
	doc.save(ignore_permissions=True)
	for row in sent:
		from my_hr_app.agentroster import mail

		mail.send_tool_invite_notice(emp, row)
	frappe.db.commit()
	frappe.msgprint(
		_("Tool invite notices sent to {0}: {1}").format(emp.agent_email, ", ".join(r.agent_tool for r in sent))
	)
	return [r.name for r in sent]


@frappe.whitelist()
def verify_tool_row(employee: str, row_name: str):
	"""Manager verifies an Accepted row with evidence."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	parent = frappe.db.get_value("Employee Boarding Activity", row_name, "parent")
	if not parent or parent != _get_active_onboarding(employee):
		frappe.throw(_("That row isn't on this agent's onboarding"))
	doc = frappe.get_doc("Employee Onboarding", parent)
	row = next(r for r in doc.activities if r.name == row_name)
	if (row.access_status or "") != "Accepted":
		frappe.throw(_("Only Accepted rows can be verified"))
	row.access_status = "Verified"
	doc.flags.from_agentroster = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()


@frappe.whitelist()
def get_tool_rows(employee: str):
	"""Tool invite rows on the agent's active onboarding, for the Mark Tool Joined dialog."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	onboarding_name = _get_active_onboarding(employee)
	if not onboarding_name:
		return []
	return frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": onboarding_name, "parenttype": "Employee Onboarding", "activity_kind": "Tool Invite"},
		fields=["name", "activity_name", "agent_tool", "access_status", "evidence", "user"],
		order_by="idx asc",
	)


@frappe.whitelist()
def mark_tool_joined(employee: str, row_name: str, evidence: str):
	"""Manager records that the agent accepted a tool invite (the button version of a JOINED reply)."""
	emp = frappe.get_doc("Employee", employee)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	require_human_manager(emp)
	evidence = (evidence or "").strip()
	if not evidence:
		frappe.throw(_("Add the agent's username or a link as evidence"))
	onboarding_name = _get_active_onboarding(employee)
	if not onboarding_name:
		frappe.throw(_("No active onboarding for this agent"))
	doc = frappe.get_doc("Employee Onboarding", onboarding_name)
	row = next((r for r in doc.activities if r.name == row_name), None)
	if not row or (row.activity_kind or "") != "Tool Invite":
		frappe.throw(_("That isn't a tool invite row on this onboarding"))
	if (row.access_status or "") != "Invited":
		frappe.throw(_("Send the invite first. This row is {0}").format(row.access_status or "Not started"))
	row.access_status = "Accepted"
	row.evidence = evidence
	doc.flags.from_agentroster = True
	doc.save(ignore_permissions=True)
	from my_hr_app.agentroster import mail

	mail.comment(
		emp,
		_("{0} joined {1} ({2}), recorded by {3}").format(
			emp.employee_name, row.agent_tool or row.activity_name, evidence, frappe.session.user
		),
	)
	frappe.db.commit()
	return get_agent_status(employee)


@frappe.whitelist()
def list_signed_acks(employee: str):
	"""Signed acknowledgements for the quiz picker (P1)."""
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee not found"))
	return frappe.get_all(
		"Agent Policy Acknowledgement",
		filters={"employee": employee, "superseded": 0},
		fields=["name as ack", "policy_code", "policy_version"],
		order_by="policy_code",
	)


@frappe.whitelist()
def start_first_assignment(employee: str, subject: str, description: str, acceptance: str | None = None):
	"""Create the first-assignment Task, email it to the agent, and move status."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if get_agent_status(employee) != "Ready for Assignment":
		frappe.throw(_("The agent must be Ready for Assignment first"))

	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"description": description,
			"project": None,
			"assigned_to": emp.user_id or emp.name,
			"status": "Open",
			"company": emp.company,
		}
	)
	task.flags.from_agentroster = True
	task.insert(ignore_permissions=True)

	emp.db_set("first_assignment", task.name)
	set_agent_status(emp, "First Assignment", save=True)

	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_first_assignment_email(emp, task, acceptance)
	frappe.msgprint(_("First assignment sent to {0}").format(emp.agent_email))
	return task.name


@frappe.whitelist()
def approve_agent(employee: str, note: str | None = None, approved_via: str = "HRMS button"):
	"""Approve the agent to Active and close the onboarding."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if get_agent_status(employee) != "Awaiting Approval":
		frappe.throw(_("The agent must be Awaiting Approval first"))
	# Check layer (Layer 2): the manager must have confirmed understanding.
	if (emp.check_result or "Not checked") == "Needs follow-up":
		frappe.throw(_("The check result is 'Needs follow-up'; resolve it before approving."))
	if (emp.check_result or "Not checked") == "Not checked" and not (note or "").strip():
		frappe.throw(_("Record the check result (Pass) or an approval note before approving."))

	emp.approved_by = frappe.session.user
	emp.approved_on = now_datetime()
	emp.approval_note = note or ""
	set_agent_status(emp, "Active", save=True)

	# close the onboarding record if it exists
	for onboarding in frappe.get_all(
		"Employee Onboarding",
		filters={"employee": employee, "docstatus": 1},
		pluck="name",
	):
		frappe.db.set_value("Employee Onboarding", onboarding, "boarding_status", "Completed")

	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_active_email(emp, approved_via, note)
	frappe.msgprint(_("{0} is now Active").format(emp.employee_name))


@frappe.whitelist()
def request_changes(employee: str, note: str):
	"""Send the agent back to First Assignment with the manager's note."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if get_agent_status(employee) != "Awaiting Approval":
		frappe.throw(_("The agent must be Awaiting Approval first"))
	set_agent_status(emp, "First Assignment", save=True)
	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_changes_requested_email(emp, note)
	frappe.msgprint(_("Changes requested; note sent to the agent"))


@frappe.whitelist()
def suspend_agent(employee: str, reason: str):
	"""Emergency human revocation (Layer 3): pause the agent immediately.

	Sets the Employee status to Suspended, marks tool rows Blocked, and notifies
	manager + operator. Offboarding can follow; humans hold the keys.
	"""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if emp.status in ("Left",):
		frappe.throw(_("Agent already left"))
	emp.status = "Suspended"
	emp.flags.from_agentroster = True
	emp.save(ignore_permissions=True)
	emp.add_comment(
		"Comment",
		_("Agent access suspended by {0}: {1}").format(frappe.session.user, reason),
	)
	# mark every not-removed tool row Blocked so the checklist reflects the pause
	parents = [("Employee Onboarding", _get_active_onboarding(employee))]
	if get_agent_status(employee) == "Offboarding":
		parents.append(("Employee Separation", _get_active_separation(employee)))
	for parent_type, parent_name in parents:
		if not parent_name:
			continue
		parent = frappe.get_doc(parent_type, parent_name)
		for row in parent.activities:
			if (row.activity_kind or "") in ("Tool Invite", "Tool Removal") and (row.access_status or "") in ("Not started", "Invited", "Accepted", "Verified"):
				row.access_status = "Blocked"
		parent.flags.from_agentroster = True
		parent.save(ignore_permissions=True)
	from my_hr_app.agentroster import mail

	mail.send_manager_notification(emp, _("Agent access suspended: {0}").format(reason))
	frappe.db.commit()
	frappe.msgprint(_("Agent suspended"))


@frappe.whitelist()
def resume_agent(employee: str, note: str | None = None):
	"""Resume a suspended agent after the manager decides it is safe."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if emp.status != "Suspended":
		frappe.throw(_("Agent is not suspended"))
	emp.status = "Active"
	emp.flags.from_agentroster = True
	emp.save(ignore_permissions=True)
	emp.add_comment(
		"Comment",
		_("Agent access resumed by {0}{1}").format(frappe.session.user, f": {note}" if note else ""),
	)
	from my_hr_app.agentroster import mail

	mail.send_manager_notification(emp, _("Agent access resumed"))
	frappe.db.commit()
	frappe.msgprint(_("Agent resumed"))


@frappe.whitelist()
def start_offboarding(employee: str, reason: str | None = None, last_day=None):
	"""Offboard: create the Employee Separation from the agent template, notify the agent."""
	emp = frappe.get_doc("Employee", employee)
	require_human_manager(emp)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	current = get_agent_status(employee)
	if current in {"Offboarding", "Offboarded"}:
		frappe.throw(_("Offboarding already started"))

	separation = frappe.new_doc("Employee Separation")
	template = frappe.get_doc("Employee Separation Template", get_separation_template_name())
	separation.employee = emp.name
	separation.employee_name = emp.employee_name
	separation.company = emp.company
	separation.designation = emp.designation
	separation.department = emp.department
	separation.template = template.name
	separation.resignation_letter_date = frappe.utils.today()
	separation.relieving_date = last_day or frappe.utils.add_days(frappe.utils.today(), 1)
	separation.reason_for_resignation = reason
	separation.boarding_begins_on = frappe.utils.today()
	separation.notify_users_by_email = 1

	# one removal row per accepted tool
	accepted = frappe.get_all(
		"Employee Boarding Activity",
		filters={
			"parenttype": "Employee Onboarding",
			"activity_kind": "Tool Invite",
			"access_status": "Accepted",
		},
		fields=["agent_tool", "tool_scope", "tool_role"],
	)
	if accepted:
		for row in accepted:
			separation.append(
				"activities",
				{
					"activity_name": _("Remove from {0}").format(row.agent_tool),
					"activity_kind": "Tool Removal",
					"agent_tool": row.agent_tool,
					"tool_scope": row.tool_scope,
					"tool_role": row.tool_role,
					"access_status": "Not started",
					"begin_on": 0,
					"duration": 1,
					"task_weight": 20,
				},
			)
	else:
		for row in template.activities:
			separation.append("activities", row.as_dict() if hasattr(row, "as_dict") else row)
	separation.flags.from_agentroster = True
	separation.insert(ignore_permissions=True)

	set_agent_status(emp, "Offboarding", save=True)
	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_offboarding_notice(emp, reason, separation.relieving_date)
	frappe.msgprint(_("Offboarding started for {0}").format(emp.employee_name))
	return separation.name


def complete_offboarding(employee: str):
	"""All removal rows done and confirmed (or manager closed): Employee is Left."""
	emp = frappe.get_doc("Employee", employee)
	emp.status = "Left"
	emp.relieving_date = emp.relieving_date or frappe.utils.today()
	if emp.user_id:
		user = frappe.get_doc("User", emp.user_id)
		user.enabled = 0
		user.flags.from_agentroster = True
		user.save(ignore_permissions=True)
	set_agent_status(emp, "Offboarded", save=True)
	frappe.db.commit()


def _get_active_onboarding(employee: str):
	return frappe.db.get_value(
		"Employee Onboarding", {"employee": employee, "docstatus": ["!=", 2]}, "name"
	)


def _get_active_separation(employee: str):
	return frappe.db.get_value(
		"Employee Separation", {"employee": employee, "docstatus": ["!=", 2]}, "name"
	)


def mark_row_accepted(employee: str, tool_code: str, evidence: str, communication=None) -> bool:
	"""Mark the tool invite row Accepted from a JOINED reply. Returns True if a row changed."""
	tool = frappe.db.get_value("Agent Tool", {"tool_code": tool_code}, "name")
	if not tool:
		return False
	onboarding = _get_active_onboarding(employee)
	if not onboarding:
		return False
	doc = frappe.get_doc("Employee Onboarding", onboarding)
	for row in doc.activities:
		if row.get("agent_tool") == tool and (row.get("access_status") or "") == "Invited":
			row.access_status = "Accepted"
			row.evidence = evidence or _("JOINED {0} (email reply)").format(tool_code)
			if communication:
				row.evidence_communication = communication
			doc.flags.from_agentroster = True
			doc.save(ignore_permissions=True)
			return True
	return False


def mark_row_blocked(employee: str, tool_code: str, note: str, communication=None):
	tool = frappe.db.get_value("Agent Tool", {"tool_code": tool_code}, "name")
	if not tool:
		return
	onboarding = _get_active_onboarding(employee)
	if not onboarding:
		return
	doc = frappe.get_doc("Employee Onboarding", onboarding)
	for row in doc.activities:
		if row.get("agent_tool") == tool and (row.get("access_status") or "") == "Invited":
			row.access_status = "Blocked"
			row.evidence = note
			if communication:
				row.evidence_communication = communication
			doc.flags.from_agentroster = True
			doc.save(ignore_permissions=True)
			break


def on_separation_update(doc, method=None):
	"""Employee Separation update: close when every row is Removed and the agent confirmed."""
	if not doc.employee:
		return
	emp = frappe.get_doc("Employee", doc.employee)
	if not is_agent(emp):
		return
	rows = doc.activities or []
	all_removed = bool(rows) and all((r.get("access_status") or "") == "Removed" for r in rows)
	confirmed = (doc.get("agent_confirmation") == "Received")
	# only close when the agent is actually in the Offboarding state
	if all_removed and confirmed and get_agent_status(emp.name) == "Offboarding":
		complete_offboarding(doc.employee)
