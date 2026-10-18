"""Policy Document on_update: publish -> re-ack requests for every Active/onboarding agent."""

import frappe
from frappe import _
from frappe.utils import add_days, today

from my_hr_app.agentroster.agent import is_agent


def on_policy_update(doc, method=None):
	if doc.status != "Published":
		return
	# only act on transitions into Published
	previous_status = None
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	if previous:
		previous_status = previous.status
	if doc.is_new() or previous_status != "Published":
		pass
	else:
		return  # already published, no re-ack fan-out

	if not doc.applies_to_agents:
		return

	agents = frappe.get_all(
		"Employee",
		filters={"worker_type": "Agent", "status": ["!=", "Left"]},
		pluck="name",
	)
	grace = doc.reack_grace_days or 3
	due = add_days(today(), grace)
	for name in agents:
		emp = frappe.get_doc("Employee", name)
		if not is_agent(emp):
			continue
		if emp.agent_status in {"Offboarding", "Offboarded", "Draft"}:
			continue
		if not policy_applies(emp, doc):
			continue
		frappe.db.set_value("Employee", name, "policy_ack_status", "Re-ack Required")
		from my_hr_app.agentroster import mail

		mail.send_ack_request(emp, doc, due_date=due)


def policy_applies(emp, doc) -> bool:
	applies_to = frappe.get_all(
		"Policy Applies To",
		filters={"parent": doc.name, "parenttype": "Policy Document"},
		pluck="designation",
	)
	if not applies_to:
		return True
	return (emp.designation or "") in applies_to
