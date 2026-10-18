import frappe


def run():
	checks = {
		"Policy Document doctype": bool(frappe.db.exists("DocType", "Policy Document")),
		"Agent Policy Acknowledgement doctype": bool(frappe.db.exists("DocType", "Agent Policy Acknowledgement")),
		"Agent Tool doctype": bool(frappe.db.exists("DocType", "Agent Tool")),
		"Email Templates": len(
			frappe.get_all("Email Template", filters={"name": ["like", "AgentRoster:%"]})
		),
		"Agent Tools seeded": frappe.get_all("Agent Tool", pluck="tool_name"),
		"Employee custom fields": len(
			frappe.get_all(
				"Custom Field",
				filters={
					"dt": "Employee",
					"fieldname": ["in", ["agent_email", "agent_status", "worker_type", "approval_code"]],
				},
			)
		),
		"Boarding Activity fields": len(
			frappe.get_all(
				"Custom Field",
				filters={
					"dt": "Employee Boarding Activity",
					"fieldname": ["in", ["activity_kind", "access_status", "evidence"]],
				},
			)
		),
		"Onboarding template": bool(
			frappe.db.exists("Employee Onboarding Template", {"title": "Agent onboarding: standard"})
		),
		"Separation template": bool(
			frappe.db.exists("Employee Separation Template", {"title": "Agent separation: standard"})
		),
	}
	for k, v in checks.items():
		print(f"{k}: {v}")
	return checks
