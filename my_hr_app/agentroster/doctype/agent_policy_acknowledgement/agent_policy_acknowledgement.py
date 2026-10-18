import frappe
from frappe import _
from frappe.model.document import Document


class AgentPolicyAcknowledgement(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		ack_text: DF.LongText
		check_note: DF.SmallText
		check_result: DF.Literal["Not checked", "Pass", "Needs follow-up"]
		checked_by: DF.Link | None
		communication: DF.Link | None
		content_hash: DF.Data | None
		employee: DF.Link
		method: DF.Literal["Email reply", "Web form", "Recorded by manager"]
		policy_code: DF.Data | None
		policy_document: DF.Link
		policy_version: DF.Int
		quiz_answers: DF.LongText
		received_at: DF.Datetime | None
		sender_verified: DF.Check
		source_email: DF.Data | None
		superseded: DF.Check
	# end: auto-generated types

	def validate(self):
		policy = frappe.get_doc("Policy Document", self.policy_document)
		if not self.policy_code:
			self.policy_code = policy.code
			self.policy_version = policy.version
			self.content_hash = policy.content_hash
		if self.method == "Email reply" and self.source_email:
			self.sender_verified = 1
		if self.method == "Recorded by manager" and not self.check_note:
			frappe.throw(_("A note is required when a manager records an acknowledgement"))

	def on_trash(self):
		frappe.throw(_("Agent Policy Acknowledgements cannot be deleted. Mark superseded instead."))


def create_acknowledgement(
	employee: str,
	policy_document: str,
	method: str = "Email reply",
	source_email: str | None = None,
	communication: str | None = None,
	ack_text: str | None = None,
	received_at=None,
) -> Document:
	"""Idempotently record the agent's acknowledgement of one policy version."""
	policy = frappe.get_doc("Policy Document", policy_document)
	existing = frappe.db.exists(
		"Agent Policy Acknowledgement",
		{
			"employee": employee,
			"policy_code": policy.code,
			"policy_version": policy.version,
			"superseded": 0,
		},
	)
	if existing:
		return frappe.get_doc("Agent Policy Acknowledgement", existing)

	ack = frappe.get_doc(
		{
			"doctype": "Agent Policy Acknowledgement",
			"employee": employee,
			"policy_document": policy.name,
			"policy_code": policy.code,
			"policy_version": policy.version,
			"content_hash": policy.content_hash,
			"method": method,
			"source_email": source_email,
			"communication": communication,
			"ack_text": ack_text,
			"received_at": received_at or frappe.utils.now_datetime(),
			"check_result": "Not checked",
		}
	)
	ack.flags.sender_email = source_email
	ack.insert(ignore_permissions=True)
	return ack
