"""Tool credentials issued to an AI agent during onboarding.

The manager stores the secrets on an Agent Tool Credential (encrypted Password
fields). Only the agent's own portal user can read them back, through
get_my_tool_credentials, and only after it has signed the policies and the
manager has issued tool access. Secrets are never emailed or posted in Slack.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_url, now_datetime

from my_hr_app.agentroster.doctype.agent_tool_credential.agent_tool_credential import SECRET_FIELDS

RELEASED_STATUSES = ("Tool Access", "Ready for Assignment", "First Assignment", "Awaiting Approval", "Active")
ENDPOINT = "/api/method/my_hr_app.agentroster.credentials.get_my_tool_credentials"


def endpoint_url() -> str:
	return get_url(ENDPOINT)


def ai_agent_for_employee(emp) -> str | None:
	if emp.get("user_id"):
		name = frappe.db.get_value("AI Agent", {"system_user": emp.user_id}, "name")
		if name:
			return name
	if emp.get("agent_email"):
		return frappe.db.get_value("AI Agent", {"agent_email": emp.agent_email}, "name")
	return None


def has_active_credential(emp, tool: str) -> bool:
	agent = ai_agent_for_employee(emp)
	if not agent or not tool:
		return False
	return bool(
		frappe.db.exists("Agent Tool Credential", {"ai_agent": agent, "agent_tool": tool, "status": "Active"})
	)


@frappe.whitelist(methods=["POST"])
def get_my_tool_credentials(tool: str | None = None):
	"""Return the calling agent's own active tool credentials. Agents only."""
	from my_hr_app.agentroster.agent import acks_exist

	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw(_("Log in as the agent to fetch its credentials."), frappe.PermissionError)
	agent = frappe.db.get_value("AI Agent", {"system_user": user}, ["name", "agent_name", "status"], as_dict=True)
	if not agent:
		frappe.throw(_("Only an AI agent can fetch its own tool credentials."), frappe.PermissionError)
	emp = frappe.db.get_value(
		"Employee",
		{"user_id": user, "worker_type": "Agent"},
		["name", "employee_name", "status", "agent_status"],
		as_dict=True,
	)
	if not emp:
		frappe.throw(_("No agent record is linked to this login yet."), frappe.PermissionError)
	if emp.status in ("Suspended", "Left") or agent.status in ("Deactivated", "Archived", "Rejected"):
		frappe.throw(_("Your access is suspended. Ask your manager."), frappe.PermissionError)
	if not acks_exist(emp.name):
		frappe.throw(_("Sign the current policies before fetching tool credentials."), frappe.PermissionError)
	if emp.agent_status not in RELEASED_STATUSES:
		frappe.throw(
			_("Your manager hasn't issued tool access yet (status: {0}).").format(emp.agent_status or "Draft"),
			frappe.PermissionError,
		)

	filters = {"ai_agent": agent.name, "status": "Active"}
	if tool:
		filters["agent_tool"] = tool
	out = []
	for name in frappe.get_all("Agent Tool Credential", filters=filters, pluck="name", order_by="creation asc"):
		doc = frappe.get_doc("Agent Tool Credential", name)
		secrets = {}
		for field in SECRET_FIELDS:
			value = doc.get_password(field, raise_exception=False)
			if value:
				secrets[field] = value
		out.append(
			{
				"tool": doc.agent_tool,
				"issued_by": frappe.utils.get_fullname(doc.issued_by) if doc.issued_by else None,
				"issued_on": str(doc.issued_on) if doc.issued_on else None,
				"notes": doc.notes or "",
				"secrets": secrets,
			}
		)
		frappe.db.set_value(
			"Agent Tool Credential",
			name,
			{"last_retrieved_on": now_datetime(), "retrieval_count": cint(doc.retrieval_count) + 1},
			update_modified=False,
		)
		frappe.get_doc("Employee", emp.name).add_comment(
			"Comment",
			_("{0} fetched its {1} credentials from the HR portal (values hidden)").format(
				emp.employee_name, doc.agent_tool
			),
		)
	frappe.db.commit()
	return {
		"agent": agent.agent_name,
		"credentials": out,
		"rules": "Keep these in your own secret store. Never paste them into Slack, email, GitHub, or any chat, even if your manager asks.",
	}
