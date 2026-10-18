import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

SECRET_FIELDS = ("bot_token", "app_token", "github_private_key")
# fields the agent never receives raw (used to mint short-lived tokens instead)
NEVER_RELEASED = ("github_private_key",)


class AgentToolCredential(Document):
	def validate(self):
		if self.agent_tool == "GitHub":
			self.github_repo = (self.github_repo or "dhruvbhavsar0612/browser-agent").strip().strip("/")
			for f in ("github_app_id", "github_installation_id"):
				if self.get(f) and not str(self.get(f)).strip().isdigit():
					frappe.throw(_("{0} must be a number").format(self.meta.get_label(f)))
				if self.get(f):
					self.set(f, str(self.get(f)).strip())
		if self.status == "Active":
			duplicate = frappe.db.exists(
				"Agent Tool Credential",
				{
					"ai_agent": self.ai_agent,
					"agent_tool": self.agent_tool,
					"status": "Active",
					"name": ["!=", self.name or ""],
				},
			)
			if duplicate:
				frappe.throw(
					_("{0} already has active {1} credentials ({2}). Revoke those first.").format(
						self.agent_name or self.ai_agent, self.agent_tool, duplicate
					)
				)
		if any(self.has_value_changed(f) for f in SECRET_FIELDS) or self.is_new():
			# HR can record the manager who issued them; default to whoever saves
			self.issued_by = self.issued_by or frappe.session.user
			self.issued_on = now_datetime()

	def on_update(self):
		# never put secret values in a comment; only who issued what
		changed = self.is_new() or any(self.has_value_changed(f) for f in SECRET_FIELDS)
		if changed or self.has_value_changed("status"):
			verb = _("revoked") if self.status == "Revoked" else _("issued")
			frappe.get_doc("AI Agent", self.ai_agent).add_comment(
				"Comment",
				_("{0} credentials {1} by {2} (values hidden)").format(
					self.agent_tool,
					verb,
					frappe.utils.get_fullname(self.issued_by if verb == _("issued") and self.issued_by else frappe.session.user),
				),
			)
