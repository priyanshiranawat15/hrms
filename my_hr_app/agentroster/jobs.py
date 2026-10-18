"""Scheduled jobs: no-reply nudges and overdue re-acks (spec 12.2)."""

import frappe
from frappe.utils import add_days, now_datetime, today

from my_hr_app.agentroster import mail


def remind_no_reply():
	"""Hourly: nudge the manager when the agent hasn't replied in 48h while onboarding."""
	cutoff = add_days(now_datetime(), -2)
	onboarding_docs = frappe.get_all(
		"Employee Onboarding",
		filters={"docstatus": 1},
		pluck="employee",
	)
	for employee in set(onboarding_docs):
		emp = frappe.get_doc("Employee", employee)
		if (emp.worker_type or "Human") != "Agent":
			continue
		last_inbound = frappe.get_all(
			"Communication",
			filters={
				"reference_doctype": "Employee",
				"reference_name": employee,
				"sent_or_received": "Received",
				"creation": [">", cutoff],
			},
			limit=1,
			pluck="name",
		)
		if not last_inbound and mail.get_manager_email(emp):
			mail.send_manager_notification(emp, "No reply in 48h from the agent")


def reack_overdue():
	"""Daily: agents with Re-ack Required past the grace date -> remind the manager."""
	policies = frappe.get_all(
		"Policy Document",
		filters={"status": "Published", "applies_to_agents": 1},
		fields=["name", "code", "version", "reack_grace_days", "effective_date"],
	)
	agents = frappe.get_all(
		"Employee",
		filters={"worker_type": "Agent", "policy_ack_status": "Re-ack Required", "status": ["!=", "Left"]},
		pluck="name",
	)
	for employee in agents:
		emp = frappe.get_doc("Employee", employee)
		for p in policies:
			acked = frappe.db.exists(
				"Agent Policy Acknowledgement",
				{
					"employee": employee,
					"policy_code": p.code,
					"policy_version": p.version,
					"superseded": 0,
				},
			)
			if acked:
				continue
			grace = p.reack_grace_days or 3
			due = add_days(p.effective_date or today(), grace)
			if today() > due and mail.get_manager_email(emp):
				mail.send_manager_notification(
					emp, f"Re-ack overdue for {p.code} v{p.version}: decide whether to pause access"
				)
