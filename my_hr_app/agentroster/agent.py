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


def set_agent_status(doc, status: str, save: bool = False):
	"""Move an agent's status, raising on an illegal transition."""
	old = get_agent_status(doc.name) if not doc.is_new() else None
	if not transition_allowed(old, status):
		frappe.throw(
			_("Illegal agent status transition: {0} -> {1}").format(old or "(new)", status)
		)
	doc.set(AGENT_STATUS_FIELD, status)
	if save:
		doc.flags.from_agentroster = True
		doc.save(ignore_permissions=True)


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

	Also syncs the agent status from the checklist rows (spec 6.1 steps 4-5).
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
	if tool_rows and all((r.get("access_status") or "") == "Accepted" for r in tool_rows):
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
	for row in template.activities:
		onboarding.append("activities", row.as_dict() if hasattr(row, "as_dict") else row)
	onboarding.flags.from_agentroster = True
	onboarding.insert(ignore_permissions=True)

	set_agent_status(emp, "Policies Sent", save=True)
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
	ack = frappe.get_doc("Agent Policy Acknowledgement", ack_name)
	policy = frappe.get_doc("Policy Document", ack.policy_document)
	if not policy.quiz_questions:
		frappe.throw(_("This policy has no quiz questions configured"))
	mail.send_quiz_email(emp, ack, policy)
	frappe.msgprint(_("Quiz sent to {0}").format(emp.agent_email))


@frappe.whitelist()
def start_first_assignment(employee: str, subject: str, description: str, acceptance: str | None = None):
	"""Create the first-assignment Task, email it to the agent, and move status."""
	emp = frappe.get_doc("Employee", employee)
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
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	if get_agent_status(employee) != "Awaiting Approval":
		frappe.throw(_("The agent must be Awaiting Approval first"))

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
	if get_agent_status(employee) != "Awaiting Approval":
		frappe.throw(_("The agent must be Awaiting Approval first"))
	set_agent_status(emp, "First Assignment", save=True)
	frappe.db.commit()
	from my_hr_app.agentroster import mail

	mail.send_changes_requested_email(emp, note)
	frappe.msgprint(_("Changes requested; note sent to the agent"))


@frappe.whitelist()
def start_offboarding(employee: str, reason: str | None = None, last_day=None):
	"""Offboard: create the Employee Separation from the agent template, notify the agent."""
	emp = frappe.get_doc("Employee", employee)
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
			row.evidence = evidence
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
	if all_removed and confirmed:
		complete_offboarding(doc.employee)
