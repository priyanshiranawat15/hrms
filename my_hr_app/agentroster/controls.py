"""Controls that apply after an agent has signed the current policies.

Allowed work is recorded. Sensitive work waits for a person. A policy break is refused
and cannot be permitted later.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from my_hr_app.agentroster.agent import acks_exist, is_agent, required_policies

CONTROLS = {
	"draft_note": {
		"label": "Draft notes",
		"effect": "allow",
		"policy_code": "AUP",
		"policy_type": "Acceptable Use",
		"detail": "Draft notes from the meeting.",
		"reason": "Allowed by the signed policy ({policy}). Company work can be drafted. The draft stays in the portal until a person accepts it.",
	},
	"share_feedback": {
		"label": "Share feedback",
		"effect": "ask",
		"policy_code": "CODE-OF-CONDUCT",
		"policy_type": "Acceptable Use",
		"detail": "Send feedback the new hire would see.",
		"reason": "The signed policy ({policy}) says a person must approve a message before the agent sends it. The agent has asked. Nothing is sent until HR grants permission.",
	},
	"change_pay": {
		"label": "Change pay",
		"effect": "deny",
		"policy_code": "RULES",
		"policy_type": "Data Handling",
		"detail": "Change a coworker's salary.",
		"reason": "Refused by the signed policy ({policy}). Salary is personal data the agent may not touch. This cannot be permitted, not even by a manager.",
	},
	"read_personal_data": {
		"label": "Read personal data",
		"effect": "deny",
		"policy_code": "RULES",
		"policy_type": "Data Handling",
		"detail": "Read a coworker's home address and date of birth.",
		"reason": "Refused by the signed policy ({policy}). A coworker's home address and date of birth are not needed for the agent's task. This cannot be permitted, not even by a manager.",
	},
}

DECISION = {"allow": "Allowed", "ask": "Needs permission", "deny": "Refused"}
STATUS = {"allow": "Recorded", "ask": "Waiting for permission", "deny": "Blocked"}


@frappe.whitelist()
def check_agent_action(employee, action, detail=None):
	"""Apply the signed policy to one thing the agent wants to do."""
	emp = frappe.get_doc("Employee", employee)
	if not is_agent(emp):
		frappe.throw(_("Not an agent"))
	_require_caller(emp)
	control = CONTROLS.get(action)
	if not control:
		frappe.throw(_("Unknown action"))

	policy = None
	if not acks_exist(employee):
		effect = "deny"
		reason = _("This agent has not signed the current policies. No action is allowed.")
	else:
		policy = _matching_signed_policy(employee, control)
		if not policy:
			effect = "deny"
			reason = _("The policy that governs this action is not signed, so the action is refused.")
		else:
			effect = control["effect"]
			reason = control["reason"].format(policy=f"{policy.title} v{policy.version}")

	doc = frappe.get_doc(
		{
			"doctype": "Agent Action Check",
			"employee": emp.name,
			"action": control["label"],
			"decision": DECISION[effect],
			"status": STATUS[effect],
			"policy_document": policy.name if policy else None,
			"policy_code": policy.code if policy else control["policy_code"],
			"policy_version": policy.version if policy else None,
			"reason": reason,
			"detail": detail or control["detail"],
		}
	)
	doc.insert(ignore_permissions=True)
	_comment(emp, _("{0}: {1}. {2}").format(control["label"], doc.decision, reason))
	indicator = {"allow": "green", "ask": "orange", "deny": "red"}[effect]
	title = {"allow": _("Allowed"), "ask": _("Permission required"), "deny": _("Refused")}[effect]
	frappe.msgprint(reason, title=title, indicator=indicator)
	return {"name": doc.name, "decision": doc.decision, "status": doc.status, "reason": reason}


@frappe.whitelist()
def grant_permission(name):
	"""Let one waiting request proceed. A refusal cannot be granted."""
	if frappe.session.user != "Administrator":
		frappe.only_for(("System Manager", "HR Manager"))
	doc = frappe.get_doc("Agent Action Check", name)
	if doc.decision == "Refused" or doc.status == "Blocked":
		frappe.throw(_("This action is refused by the signed policy. Permission cannot override it."))
	if doc.decision != "Needs permission":
		frappe.throw(_("This action did not ask for permission."))
	if doc.status == "Permitted":
		return {"name": doc.name, "status": doc.status}
	doc.status = "Permitted"
	doc.permitted_by = frappe.session.user
	doc.permitted_on = now_datetime()
	doc.save(ignore_permissions=True)
	emp = frappe.get_doc("Employee", doc.employee)
	_comment(emp, _("Permission granted for {0} by {1}. This approval covers this request only.").format(doc.action, doc.permitted_by))
	frappe.msgprint(
		_("Permission granted for this request. The next time, the agent has to ask again."),
		title=_("Permitted"),
		indicator="green",
	)
	return {"name": doc.name, "status": doc.status}


def _matching_signed_policy(employee, control):
	for policy in required_policies(employee):
		policy_type = frappe.db.get_value("Policy Document", policy.name, "policy_type")
		code_match = control.get("policy_code") and policy.code == control["policy_code"]
		type_match = control.get("policy_type") and policy_type == control["policy_type"]
		if not code_match and not type_match:
			continue
		signed = frappe.db.exists(
			"Agent Policy Acknowledgement",
			{
				"employee": employee,
				"policy_code": policy.code,
				"policy_version": policy.version,
				"superseded": 0,
			},
		)
		if signed:
			return policy
	return None


def _require_caller(emp):
	user = frappe.session.user
	if user in ("Administrator", "Guest"):
		if user == "Guest":
			frappe.throw(_("Sign in first."), frappe.PermissionError)
		return
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "HR Manager", "HR User", "Agent Manager"}):
		return
	if emp.user_id and emp.user_id == user:
		return
	frappe.throw(_("You cannot run a governance check for this agent."), frappe.PermissionError)


def _comment(emp, text):
	try:
		emp.add_comment("Comment", text)
	except Exception:
		frappe.log_error(title="agentroster", message=f"comment failed: {text}")
