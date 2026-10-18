import frappe
from frappe import _

AGENT_USER_TYPE = "Agent System User"


def prevent_agent_self_signup(doc, method=None):
	"""HR creates the agent account. The agent cannot register itself."""
	if doc.user_type != AGENT_USER_TYPE or doc.flags.get("from_agent_registry"):
		return
	if frappe.flags.get("in_provision_agent"):
		return
	if not doc.is_new() and frappe.db.exists("AI Agent", {"system_user": doc.name}):
		return
	frappe.throw(
		_("AI agents cannot create their own account. HR registers the agent, then the agent signs in with that account.")
	)


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
