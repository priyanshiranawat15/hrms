import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, get_url, now_datetime

AGENT_USER_TYPE = "Agent System User"
INVITE_DAYS = 7


def prevent_agent_self_signup(doc, method=None):
	"""An AI agent can create a portal account only from an HR invite link."""
	if doc.user_type != AGENT_USER_TYPE or doc.flags.get("from_agent_registry"):
		return
	if doc.flags.get("from_agent_invite") or frappe.flags.get("in_agent_invite"):
		return
	if frappe.flags.get("in_provision_agent"):
		return
	if not doc.is_new() and frappe.db.exists("AI Agent", {"system_user": doc.name}):
		return
	frappe.throw(
		_("An AI agent can sign up only with an invite link from HR. Human users use the regular sign up.")
	)


@frappe.whitelist(allow_guest=True)
def human_sign_up(email, full_name, redirect_to):
	"""Public sign up stays for humans. AI agents are sent to their invite link."""
	kind = (frappe.form_dict.get("user_kind") or "Human").strip()
	if kind in ("AI Agent", "AI", AGENT_USER_TYPE):
		frappe.throw(_("An AI agent can sign up only with an invite link from HR."))

	email = (email or "").strip().lower()
	if email and frappe.db.exists("AI Agent", {"agent_email": email}):
		frappe.throw(_("This email belongs to an AI agent. Open the invite link to sign up."))

	from frappe.core.doctype.user.user import sign_up

	return sign_up(email, full_name, redirect_to)


@frappe.whitelist()
def send_portal_invite(agent_name):
	if frappe.session.user != "Administrator":
		frappe.only_for(("System Manager", "HR Manager", "HR User"))
	return issue_portal_invite(agent_name)


def issue_portal_invite(agent_name):
	agent = frappe.get_doc("AI Agent", agent_name)
	if agent.system_user and frappe.db.exists("User", agent.system_user):
		frappe.throw(_("This agent already has a portal account. The agent signs in with that email."))
	if agent.status in ("Rejected", "Archived", "Deactivated"):
		frappe.throw(_("This agent cannot be invited to the portal."))
	if agent.invite_status == "Sent" and agent.invite_key and agent.portal_invite_link:
		if not agent.invite_expires_on or get_datetime(agent.invite_expires_on) >= now_datetime():
			return agent.portal_invite_link

	from my_hr_app.agent_registry.doctype.ai_agent.ai_agent import agent_email

	email = (agent.agent_email or agent_email(agent.agent_name, agent.company)).strip().lower()
	key = frappe.generate_hash(length=32)
	expires = add_days(now_datetime(), INVITE_DAYS)
	link = get_url(f"/agent-signup?key={key}")
	agent.db_set(
		{
			"agent_email": email,
			"invite_key": key,
			"invite_status": "Sent",
			"invite_sent_on": now_datetime(),
			"invite_expires_on": expires,
			"portal_invite_link": link,
		}
	)
	if _can_send_email():
		try:
			frappe.sendmail(
				recipients=[email],
				subject=_("Your portal invite"),
				message=_("Open this link to create your AI agent account. It expires in {0} days.<br>{1}").format(
					INVITE_DAYS, link
				),
				now=True,
			)
		except Exception:
			try:
				frappe.log_error(title="Agent portal invite email failed", message=frappe.get_traceback())
			except Exception:
				pass
	return link


def _can_send_email():
	"""Skip sending when the site has no outgoing mailbox, so the invite link still shows."""
	return bool(
		frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
		or frappe.conf.get("mail_server")
	)


@frappe.whitelist(allow_guest=True)
def get_agent_invite(key):
	return _invite_row(key)


@frappe.whitelist(allow_guest=True)
def accept_agent_invite(key, full_name, password):
	row = _invite_row(key)
	if not row:
		frappe.throw(_("This invite link is invalid or has expired."))
	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Full name is required."))
	if not password or len(password) < 8:
		frappe.throw(_("Use a password of at least 8 characters."))
	if frappe.db.exists("User", row.agent_email):
		frappe.throw(_("An account already exists for this invite. Sign in instead."))

	parts = full_name.split()
	frappe.flags.in_agent_invite = True
	try:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": row.agent_email,
				"first_name": parts[0],
				"last_name": " ".join(parts[1:]),
				"user_type": AGENT_USER_TYPE,
				"send_welcome_email": 0,
				"enabled": 1,
				"new_password": password,
			}
		)
		user.flags.from_agent_invite = True
		user.flags.no_welcome_mail = True
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)

		agent = frappe.get_doc("AI Agent", row.name)
		agent.db_set(
			{
				"system_user": user.name,
				"invite_status": "Accepted",
				"invite_key": "",
				"portal_invite_link": "",
			}
		)

		from my_hr_app.agent_registry.doctype.ai_agent.ai_agent import _issue_api_secret, grant_roles

		user.flags.from_agent_invite = True
		secret = _issue_api_secret(user)
		user.reload()
		grant_roles(user.name, [AGENT_USER_TYPE])

		from my_hr_app.agent_registry.employee_split import _grant_scope, ensure_agent_employee

		employee = ensure_agent_employee(agent, user)
		_grant_scope(user.name, employee)
	finally:
		frappe.flags.in_agent_invite = False

	return {
		"email": user.email,
		"api_key": user.api_key,
		"api_secret": secret,
	}


def _invite_row(key):
	if not key:
		return None
	row = frappe.db.get_value(
		"AI Agent",
		{"invite_key": key, "invite_status": "Sent"},
		["name", "agent_name", "agent_email", "invite_expires_on", "status"],
		as_dict=True,
	)
	if not row or row.status in ("Rejected", "Archived", "Deactivated"):
		return None
	if row.invite_expires_on and get_datetime(row.invite_expires_on) < now_datetime():
		return None
	return row


def agreement_permission_query(user):
	return _linked_query(user, "Agent Business Agreement")


def sop_permission_query(user):
	return _linked_query(user, "Agent SOP")


def access_policy_permission_query(user):
	return _linked_query(user, "Agent Access Policy")


def onboarding_permission_query(user):
	return _linked_query(user, "Agent Onboarding")


def usage_permission_query(user):
	return _linked_query(user, "Agent Usage Log")


def _linked_query(user, doctype):
	if not _is_agent_user(user):
		return None
	agent = frappe.db.get_value("AI Agent", {"system_user": user}, "name")
	if not agent:
		return "1=0"
	return f"`tab{doctype}`.`ai_agent` = {frappe.db.escape(agent)}"


def _is_agent_user(user):
	return frappe.db.get_value("User", user, "user_type") == AGENT_USER_TYPE
