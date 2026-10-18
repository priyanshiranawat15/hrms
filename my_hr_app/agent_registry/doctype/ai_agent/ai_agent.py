import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

ALLOWED_TRANSITIONS = {
	None: {"Requested"},
	"Requested": {"Requested", "Under Review"},
	"Under Review": {"Under Review", "Approved", "Rejected"},
	"Approved": {"Approved", "Onboarding"},
	"Onboarding": {"Onboarding", "Active"},
	"Active": {"Active", "Deactivated", "Archived"},
	"Deactivated": {"Deactivated", "Active", "Archived"},
	"Rejected": {"Rejected", "Requested"},
	"Archived": {"Archived"},
}


class AIAgent(Document):
	def validate(self):
		if not self.agent_type:
			self.agent_type = "In-house"
		if not self.execution_mode:
			self.execution_mode = "Delegate"
		if self.agent_email:
			self.agent_email = self.agent_email.strip().lower()
		self.validate_email_locked()
		self.validate_status_transition()
		if self.status == "Active":
			blockers = self.activation_blockers()
			if blockers:
				frappe.throw("<br>".join(blockers), title=_("Agent is not ready to activate"))

	def after_insert(self):
		if self.flags.get("skip_portal_invite"):
			return
		if self.status in ("Rejected", "Archived", "Deactivated"):
			return
		from my_hr_app.agent_registry.auth import issue_portal_invite

		link = issue_portal_invite(self.name)
		self.reload()
		email = self.agent_email
		frappe.msgprint(
			_("Invite sent to {0}. The agent opens this link, sets a password, and then signs in with that email.<br>{1}").format(
				email, link
			),
			title=_("Portal invite"),
			indicator="green",
		)

	def on_update(self):
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else None
		if self.status == previous_status:
			return

		if self.status == "Approved":
			if not (self.system_user and frappe.db.exists("User", self.system_user)):
				from my_hr_app.agent_registry.auth import issue_portal_invite

				issue_portal_invite(self.name)
		elif self.status == "Onboarding":
			self.ensure_onboarding()
		elif self.status == "Active":
			self.db_set("activation_date", self.activation_date or today())
			if previous_status == "Deactivated":
				self.reissue_credentials()
		elif self.status in ("Deactivated", "Archived"):
			self.revoke_credentials()

	def validate_email_locked(self):
		previous = self.get_doc_before_save()
		if not previous or not previous.agent_email or previous.agent_email == self.agent_email:
			return
		if previous.system_user or previous.invite_status in ("Sent", "Accepted"):
			frappe.throw(
				_("This invite was already sent to {0}. The agent signs in with that email.").format(
					previous.agent_email
				)
			)

	def validate_status_transition(self):
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else None
		if self.is_new():
			previous_status = None
		allowed = ALLOWED_TRANSITIONS.get(previous_status, set())
		if self.status not in allowed and not self.flags.get("ignore_status_transition"):
			frappe.throw(
				_("Cannot move an agent from {0} to {1}.").format(previous_status or _("New"), self.status)
			)

	def activation_blockers(self):
		if not self.name:
			return [_("Save the agent before activation.")]
		blockers = []
		if not frappe.db.exists("Agent Business Agreement", {"ai_agent": self.name, "docstatus": 1}):
			blockers.append(_("Submit an Agent Business Agreement."))
		if not frappe.db.exists("Agent SOP", {"ai_agent": self.name, "docstatus": 1}):
			blockers.append(_("Submit an Agent SOP."))
		if not frappe.db.exists("Agent Access Policy", {"ai_agent": self.name, "docstatus": 1}):
			blockers.append(_("Submit an Agent Access Policy."))
		onboarding = frappe.db.get_value(
			"Agent Onboarding", {"ai_agent": self.name, "docstatus": 1}, "boarding_status"
		)
		if onboarding != "Completed":
			blockers.append(_("Complete the Agent Onboarding checklist."))
		return blockers

	def provision_system_user(self):
		if self.system_user and frappe.db.exists("User", self.system_user):
			return

		email = agent_email(self.agent_name, self.company)
		frappe.flags.in_provision_agent = True
		try:
			if frappe.db.exists("User", email):
				user = frappe.get_doc("User", email)
			else:
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": self.agent_name,
						"user_type": "Agent System User",
						"send_welcome_email": 0,
						"enabled": 1,
					}
				)
				user.flags.from_agent_registry = True
				user.flags.no_welcome_mail = True
				user.insert(ignore_permissions=True)

			user.flags.from_agent_registry = True
			user.user_type = "Agent System User"
			user.enabled = 1
			user.send_welcome_email = 0
			user.save(ignore_permissions=True)
			secret = _issue_api_secret(user)
			user.reload()
			grant_roles(user.name, ["Agent System User"])
		finally:
			frappe.flags.in_provision_agent = False

		self.db_set(
			{
				"system_user": user.name,
				"agent_email": user.email,
				"api_key": user.api_key,
				"api_key_issued_on": frappe.utils.now(),
			}
		)
		frappe.msgprint(
			_("API credentials for {0}. The secret is shown once and is not stored on the agent.<br>API Key: {1}<br>API Secret: {2}").format(
				user.email, user.api_key, secret
			),
			title=_("Agent credentials issued"),
			indicator="green",
		)

	def reissue_credentials(self):
		if not self.system_user:
			frappe.throw(_("This agent has not accepted the portal invite yet."))
			return
		user = frappe.get_doc("User", self.system_user)
		user.flags.from_agent_registry = True
		user.enabled = 1
		user.save(ignore_permissions=True)
		secret = _issue_api_secret(user)
		user.reload()
		self.restore_granted_roles()
		self.db_set({"api_key": user.api_key, "api_key_issued_on": frappe.utils.now()})
		frappe.msgprint(
			_("New API secret for {0}: {1}").format(user.email, secret),
			title=_("Credentials reissued"),
			indicator="green",
		)

	def revoke_credentials(self):
		if not self.system_user or not frappe.db.exists("User", self.system_user):
			return
		user = frappe.get_doc("User", self.system_user)
		user.flags.from_agent_registry = True
		user.enabled = 0
		user.api_secret = None
		user.save(ignore_permissions=True)

	def restore_granted_roles(self):
		if not self.system_user:
			return
		roles = ["Agent System User"]
		for policy in frappe.get_all(
			"Agent Access Policy", filters={"ai_agent": self.name, "docstatus": 1}, pluck="name"
		):
			roles.extend(frappe.get_all("Agent Access Role", filters={"parent": policy}, pluck="role"))
		grant_roles(self.system_user, roles)

	def ensure_onboarding(self):
		from my_hr_app.agent_registry.setup import TEMPLATE_TITLE

		if frappe.db.exists("Agent Onboarding", {"ai_agent": self.name, "docstatus": ["!=", 2]}):
			return
		if not frappe.db.exists("Agent Onboarding Template", TEMPLATE_TITLE):
			return

		onboarding = frappe.get_doc(
			{
				"doctype": "Agent Onboarding",
				"ai_agent": self.name,
				"agent_onboarding_template": TEMPLATE_TITLE,
				"company": self.company,
				"department": self.department,
				"designation": self.designation,
				"employee_name": self.agent_name,
				"boarding_begins_on": today(),
				"holiday_list": frappe.db.get_value("Company", self.company, "default_holiday_list"),
			}
		)
		for activity in frappe.get_all(
			"Employee Boarding Activity",
			filters={"parent": TEMPLATE_TITLE, "parenttype": "Agent Onboarding Template"},
			fields=[
				"activity_name",
				"role",
				"user",
				"required_for_employee_creation",
				"description",
				"task_weight",
				"begin_on",
				"duration",
			],
			order_by="idx",
		):
			onboarding.append("activities", activity)
		onboarding.insert(ignore_permissions=True)
		onboarding.submit()


def agent_email(agent_name, company):
	slug = frappe.scrub(agent_name).replace("_", "-")
	domain = "agents.local"
	company_email = frappe.db.get_value("Company", company, "email") if company else None
	if company_email and "@" in company_email:
		domain = company_email.split("@", 1)[1]
	return f"agent-{slug}@{domain}"


def _issue_api_secret(user):
	secret = frappe.generate_hash(length=15)
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=15)
	user.api_secret = secret
	user.save(ignore_permissions=True)
	return secret


def grant_roles(user_name, roles):
	"""Insert roles directly. User Type validation wipes roles on every User save."""
	for role in roles:
		if not role:
			continue
		if frappe.db.exists("Has Role", {"parent": user_name, "parenttype": "User", "role": role}):
			continue
		role_row = frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": user_name,
				"parenttype": "User",
				"parentfield": "roles",
				"role": role,
			}
		)
		role_row.idx = frappe.db.count("Has Role", {"parent": user_name, "parenttype": "User"}) + 1
		role_row.db_insert()
