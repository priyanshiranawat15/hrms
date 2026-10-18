import frappe
from frappe import _
from frappe.model.document import Document


class AgentAccessPolicy(Document):
	def on_submit(self):
		system_user = frappe.db.get_value("AI Agent", self.ai_agent, "system_user")
		if not system_user:
			frappe.throw(_("Approve the agent so a system user exists before submitting an access policy."))

		from my_hr_app.agent_registry.doctype.ai_agent.ai_agent import grant_roles

		# Saving a non-standard user type clears its role table, so extra roles are inserted after that save.
		grant_roles(system_user, [row.role for row in self.roles])

		for row in self.user_permissions:
			if frappe.db.exists(
				"User Permission",
				{"user": system_user, "allow": row.reference_doctype, "for_value": row.permission_value},
			):
				continue
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": system_user,
					"allow": row.reference_doctype,
					"for_value": row.permission_value,
				}
			).insert(ignore_permissions=True)
