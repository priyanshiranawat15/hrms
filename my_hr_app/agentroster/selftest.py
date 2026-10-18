import frappe


def debug_ack():
	frappe.set_user("Administrator")
	ack = frappe.get_doc(
		"Agent Policy Acknowledgement", {"employee": frappe.get_value("Employee", {"worker_type": "Agent", "employee_name": "Grok Bot"}, "name"), "policy_code": "RULES", "superseded": 0}
	)
	ack.reload()
	from frappe.model.document import get_controller
	controller = get_controller(ack.doctype)
	out = {"name": ack.name, "controller": controller.__name__, "has_on_update": hasattr(controller, "on_update")}
	try:
		out["on_update_code"] = controller.on_update.__code__.co_filename.split("apps/")[-1]
	except Exception:
		pass
	ack.ack_text = f"tampered {frappe.utils.now()}"
	try:
		out["pre_stored"] = frappe.db.get_value("Agent Policy Acknowledgement", ack.name, "ack_text")
		ack.save(ignore_permissions=True)
		out["save"] = "SAVED (no throw)"
		out["stored_text"] = frappe.db.get_value("Agent Policy Acknowledgement", ack.name, "ack_text")[:50]
	except Exception as e:
		out["save"] = f"THREW: {str(e)[:120]}"
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
