"""Tests for the policy-decision engine (controls.py) added in 3cef52dc1."""

import frappe

from my_hr_app.agentroster.governance import create_second_agent, insert_comm, log, STEPS


def run():
	frappe.set_user("Administrator")
	from my_hr_app.agentroster import controls
	from my_hr_app.agentroster import smoke as smoke_mod

	company = smoke_mod.ensure_company()
	priya = smoke_mod.ensure_manager(company)

	# ---- unsigned agent: everything is refused (rule: no signature, no action)
	emp2 = create_second_agent(company, priya)
	res = frappe.call(controls.check_agent_action, employee=emp2.name, action="draft_note")
	log("controls unsigned -> denied", res["decision"] == "Refused")

	# ---- signed agent: allow / ask / deny
	emp = smoke_mod.ensure_agent(company, priya)
	frappe.db.set_value("Employee", emp.name, "agent_status", "Policies Sent")
	frappe.db.set_value("Employee", emp.name, "policy_ack_status", "Pending")
	frappe.db.set_value("Employee", emp.name, "status", "Active")
	frappe.db.sql("update `tabPolicy Document` set status = 'Retired' where code = 'GOVREACK' or (code = 'RULES' and version > 1)")
	# supersede leftover acks so this run's ACK creates fresh evidence and moves the status
	frappe.db.sql("update `tabAgent Policy Acknowledgement` set superseded = 1 where employee = %s", emp.name)
	frappe.db.commit()

	# sign all three
	insert_comm(emp, "ACK RULES v1, CODE-OF-CONDUCT v1, AUP v1\nI will follow all Acme rules.")
	log("signed", frappe.db.get_value("Employee", emp.name, "agent_status") == "Policies Acknowledged")

	res = frappe.call(controls.check_agent_action, employee=emp.name, action="draft_note")
	log("controls allow (draft notes)", res["decision"] == "Allowed", res["status"])

	res = frappe.call(controls.check_agent_action, employee=emp.name, action="share_feedback")
	log("controls ask (feedback)", res["decision"] == "Needs permission", res["status"])
	check_name = res["name"]

	# grant requires an HR role; refusal can never be granted
	expect = frappe.get_doc("Agent Action Check", check_name)
	frappe.call(controls.grant_permission, name=check_name)
	expect.reload()
	log("controls permission granted", expect.status == "Permitted" and expect.permitted_by == "Administrator")

	res = frappe.call(controls.check_agent_action, employee=emp.name, action="change_pay")
	log("controls deny (pay)", res["decision"] == "Refused")
	deny_name = res["name"]

	try:
		frappe.call(controls.grant_permission, name=deny_name)
		log("controls denial cannot be granted", False)
	except Exception as e:
		log("controls denial cannot be granted", "cannot override" in str(e).lower() or "refused" in str(e).lower())

	res = frappe.call(controls.check_agent_action, employee=emp.name, action="read_personal_data")
	log("controls deny (personal data)", res["decision"] == "Refused")

	frappe.db.commit()
	return STEPS
