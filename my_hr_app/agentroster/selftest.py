import frappe


def debug_ack():
	"""Diagnostics: verify transactional rollback of direct db writes in this context."""
	frappe.set_user("Administrator")
	frappe.db.set_value("Employee", "HR-EMP-00002", "check_note", "rollback-test")
	out = {"after_set": frappe.db.get_value("Employee", "HR-EMP-00002", "check_note")}
	frappe.db.rollback()
	out["after_rollback"] = frappe.db.get_value("Employee", "HR-EMP-00002", "check_note")
	out["rollback_works"] = out["after_rollback"] != "rollback-test"
	return out


def repair_policies():
	"""Clean tamper-test residue from demo policies and restore their content hashes."""
	from my_hr_app.agentroster.doctype.policy_document.policy_document import hashlib_sha256

	frappe.set_user("Administrator")
	clean = {
		"RULES-v1": (
			"RULES",
			"Rules of Agreement",
			"You are an agent of Acme. Work in our tools. Follow our rules.",
		),
		"CODE-OF-CONDUCT-v1": (
			"CODE-OF-CONDUCT",
			"Code of Conduct",
			"Be respectful. Do not exfiltrate data. Escalate to your manager.",
		),
		"AUP-v1": (
			"AUP",
			"Acceptable Use",
			"Use company tools for company work. No side jobs.",
		),
	}
	for name, (code, title, body) in clean.items():
		if not frappe.db.exists("Policy Document", name):
			continue
		frappe.db.set_value(
			"Policy Document",
			name,
			{"body": body, "content_hash": hashlib_sha256(body), "change_summary": ""},
		)
	return "policies clean"
