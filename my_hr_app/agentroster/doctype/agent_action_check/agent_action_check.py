import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AgentActionCheck(Document):
	def validate(self):
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		if previous.decision != self.decision or previous.action != self.action:
			frappe.throw(_("The decision is fixed by the signed policy."))
		if previous.decision == "Refused" and self.status != "Blocked":
			frappe.throw(_("A refused action stays refused. Permission cannot override the policy."))
		if previous.decision == "Allowed" and self.status != "Recorded":
			frappe.throw(_("An allowed action is already recorded."))
		if self.status == "Permitted" and previous.status != "Permitted":
			if self.decision != "Needs permission":
				frappe.throw(_("Only a request that asks for permission can be granted."))
			self.permitted_by = frappe.session.user
			self.permitted_on = now_datetime()
