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

	IMMUTABLE_FIELDS = ("policy_document", "policy_code", "policy_version", "content_hash", "ack_text")

	def validate(self):
		# Acknowledgements are signed evidence; edits break the audit chain (T18).
		# Checked pre-write: immutability must block the UPDATE itself.
		if not self.is_new() and not self.flags.from_agentroster:
			previous = frappe.db.get_value(
				"Agent Policy Acknowledgement",
				self.name,
				list(self.IMMUTABLE_FIELDS),
				as_dict=True,
			)
			if previous:
				for field in self.IMMUTABLE_FIELDS:
					if (previous.get(field) or "") != (self.get(field) or ""):
						frappe.throw(
							_("Acknowledgement evidence is immutable. The manager can supersede it instead.")
						)
		policy = frappe.get_doc("Policy Document", self.policy_document)
		if not self.policy_code:
			self.policy_code = policy.code
			self.policy_version = policy.version
			self.content_hash = policy.content_hash
		# the signed hash must still match the published policy text (tamper chain)
		elif self.content_hash != policy.content_hash:
			frappe.throw(
				_("Acknowledged content does not match the published policy version; re-acknowledge.")
			)
		if self.method == "Email reply" and self.source_email:
			self.sender_verified = 1
		if self.method == "Recorded by manager" and not self.check_note:
			frappe.throw(_("A note is required when a manager records an acknowledgement"))

	def on_update(self):
		# Signing the last required policy makes the agent's ack status Current
		# (also clears Re-ack Required after a re-sign). Not set by the quiz.
		from my_hr_app.agentroster.agent import acks_exist

		if self.employee and not self.superseded and acks_exist(self.employee):
			frappe.db.set_value("Employee", self.employee, "policy_ack_status", "Current")

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
