import frappe
from frappe import _
from frappe.model.document import Document


class AgentBusinessAgreement(Document):
	def validate(self):
		if not self.accountable_owner:
			self.accountable_owner = frappe.db.get_value("AI Agent", self.ai_agent, "owner_employee")
		if self.docstatus == 1 and not self.signed_by_owner:
			frappe.throw(_("The human owner must sign the agreement before it can be submitted."))
