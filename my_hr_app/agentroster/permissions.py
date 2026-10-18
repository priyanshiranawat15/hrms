"""Permissions (spec 12.4): Agent Manager sees only their own agents; HR sees all.

T17: a non-owner manager cannot open another manager's agent.
"""

import frappe
from frappe import _


def get_user_employee(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if user in ("Administrator",):
		return None
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def is_agent_manager(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return bool(frappe.db.exists("Has Role", {"parent": user, "role": "Agent Manager", "parenttype": "User"}))


def permission_query_conditions(user: str | None = None) -> str:
	"""List-view scoping: non-HR agent managers only see agents they own."""
	if not is_agent_manager(user):
		return ""
	user_emp = get_user_employee(user)
	if not user_emp:
		# not an employee (e.g. an operator account) - see nothing agent-specific
		return "1=0"
	return (
		f"(`tabEmployee`.reports_to = {frappe.db.escape(user_emp)}"
		f" or `tabEmployee`.inviting_manager = {frappe.db.escape(user_emp)})"
	)


def has_permission(doc, ptype=None, user=None) -> bool:
	user = user or frappe.session.user
	if frappe.has_role(user, "HR Manager") or frappe.has_role(user, "HR User"):
		return True
	if not is_agent_manager(user):
		return False
	user_emp = get_user_employee(user)
	if not user_emp:
		return False
	return doc.get("reports_to") == user_emp or doc.get("inviting_manager") == user_emp
