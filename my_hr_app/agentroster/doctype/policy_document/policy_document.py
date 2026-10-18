import frappe
from frappe import _
from frappe.model.document import Document


class PolicyDocument(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		applies_to_agents: DF.Check
		applies_to_designations: DF.Table[PolicyAppliesTo]
		body: DF.TextEditor
		change_summary: DF.SmallText
		code: DF.Data
		content_hash: DF.Data | None
		effective_date: DF.Date | None
		policy_type: DF.Literal[
			"Rules of Agreement",
			"Code of Conduct",
			"Acceptable Use",
			"Security",
			"Data Handling",
			"Other",
		]
		quiz_questions: DF.Table[PolicyQuizQuestion]
		reack_grace_days: DF.Int
		status: DF.Literal["Draft", "Published", "Retired"]
		supersedes: DF.Link | None
		title: DF.Data
		version: DF.Int
	# end: auto-generated types

	def validate(self):
		if not self.code:
			frappe.throw(_("Policy code is required"))
		if not self.version:
			frappe.throw(_("Policy version is required"))
		duplicate = frappe.db.exists(
			"Policy Document",
			{"code": self.code, "version": self.version, "name": ["!=", self.name]},
		)
		if duplicate:
			frappe.throw(
				_("Policy Document {0} v{1} already exists: {2}").format(
					self.code, self.version, duplicate
				)
			)
		if self.status == "Published":
			self.compute_content_hash()
		elif self.status == "Draft":
			self.content_hash = None
		# Tamper-evidence: a published (or retired) policy body is frozen.
		# Any change to its text must go through a new version that supersedes it.
		elif self.status == "Retired":
			pass
		if self.status in ("Published", "Retired") and self.content_hash:
			stored_hash = None
			if not self.is_new():
				stored_hash = frappe.db.get_value("Policy Document", self.name, "content_hash")
			if stored_hash and stored_hash != self.content_hash:
				frappe.throw(
					_(
						"A published policy's body cannot be changed. Publish a new version that supersedes this one."
					)
				)

	def compute_content_hash(self):
		if not self.body:
			frappe.throw(_("Cannot publish a Policy Document without a body"))
		self.content_hash = hashlib_sha256(self.body)

	def after_rename(self, olddn, newdn, merge=False):
		pass


def hashlib_sha256(text):
	import hashlib

	return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:32]
