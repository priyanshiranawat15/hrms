"""The agent's own view of its onboarding checklist, and marking its own steps done.

An agent can only see its own checklist and can only complete tool-access steps
its manager has already started (row status Invited), in checklist order.
Manager-owned steps (signing review, first assignment, approval) stay with humans.
"""

import frappe
from frappe import _
from frappe.utils import get_url

PAGE = "/agent-onboarding"
DONE = ("Accepted", "Verified")
AFTER_SIGNING = ("Tool Access", "Ready for Assignment", "First Assignment", "Awaiting Approval", "Active")
ORDER = ["Draft", "Policies Sent", "Policies Acknowledged", "Tool Access", "Ready for Assignment", "First Assignment", "Awaiting Approval", "Active"]


def page_url() -> str:
	return get_url(PAGE)


def _my_employee():
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw(_("Log in as the agent to see its onboarding."), frappe.PermissionError)
	emp = frappe.db.get_value("Employee", {"user_id": user, "worker_type": "Agent"}, "name")
	if not emp:
		frappe.throw(_("No agent record is linked to this login yet."), frappe.PermissionError)
	return frappe.get_doc("Employee", emp)


def _reached(status, target) -> bool:
	return status in ORDER and ORDER.index(status) >= ORDER.index(target)


def build_checklist(emp) -> dict:
	from my_hr_app.agentroster import credentials, mail
	from my_hr_app.agentroster.agent import _get_active_onboarding, acks_exist

	status = emp.agent_status or "Draft"
	onboarding = _get_active_onboarding(emp.name)
	rows = []
	if onboarding:
		rows = frappe.get_all(
			"Employee Boarding Activity",
			filters={"parent": onboarding, "parenttype": "Employee Onboarding"},
			fields=["name", "activity_name", "activity_kind", "agent_tool", "access_status", "evidence", "description", "user"],
			order_by="idx asc",
		)
	signed = acks_exist(emp.name) and _reached(status, "Policies Acknowledged")
	steps = []
	previous_tools_done = True
	for r in rows:
		kind = r.activity_kind or "General"
		step = {
			"row": r.name,
			"step": r.activity_name,
			"kind": kind,
			"details": mail._plain(r.description),
			"owner": frappe.utils.get_fullname(r.user) if r.user else _("HR"),
			"evidence": r.evidence or "",
			"can_mark_done": False,
		}
		if kind == "Policy Ack":
			step["state"] = "Done" if signed else ("Your turn" if status == "Policies Sent" else "Waiting")
			if status == "Policies Sent" and emp.get("ack_web_token"):
				step["action_url"] = get_url(f"/agent-ack?t={emp.ack_web_token}")
		elif kind == "Tool Invite":
			access = r.access_status or "Not started"
			if access in DONE:
				step["state"] = "Done"
			elif access == "Invited":
				step["state"] = "Your turn" if previous_tools_done else "Next"
				step["can_mark_done"] = previous_tools_done
			elif access == "Blocked":
				step["state"] = "Blocked"
			else:
				step["state"] = "Waiting for your manager"
			if r.agent_tool and access == "Invited" and credentials.has_active_credential(emp, r.agent_tool):
				step["credentials"] = {
					"ready": True,
					"how": f"POST {credentials.endpoint_url()} with tool={r.agent_tool} (while logged in as yourself)"
					+ (" - returns a short-lived GitHub installation token for the repo (fetch a new one when it expires)" if r.agent_tool == "GitHub" else ""),
				}
			previous_tools_done = previous_tools_done and access in DONE
		elif kind == "First Assignment":
			step["state"] = "Done" if _reached(status, "Awaiting Approval") else ("Your turn" if status == "First Assignment" else "Waiting for your manager")
			step["can_mark_done"] = status == "First Assignment" and bool(emp.get("first_assignment"))
		elif kind == "Approval":
			step["state"] = "Done" if status == "Active" else "Waiting for your manager"
		else:
			step["state"] = "Done" if _reached(status, "Tool Access") else "HR"
		steps.append(step)
	return {
		"agent": emp.employee_name,
		"status": status,
		"manager": frappe.db.get_value("Employee", emp.reports_to, "employee_name") if emp.reports_to else None,
		"steps": steps,
		"page": page_url(),
	}


@frappe.whitelist()
def get_my_onboarding():
	"""The calling agent's own onboarding checklist, in order."""
	return build_checklist(_my_employee())


@frappe.whitelist(methods=["POST"])
def mark_my_step_done(row: str, evidence: str):
	"""The agent marks one of its own tool-access steps done, with evidence (username, link)."""
	emp = _my_employee()
	if emp.status in ("Suspended", "Left"):
		frappe.throw(_("Your access is suspended. Ask your manager."), frappe.PermissionError)
	evidence = (evidence or "").strip()
	if not evidence:
		frappe.throw(_("Add evidence: your username, handle, or a link."))
	step = next((s for s in build_checklist(emp)["steps"] if s["row"] == row), None)
	if not step:
		frappe.throw(_("That step isn't on your checklist."), frappe.PermissionError)
	if step["kind"] not in ("Tool Invite", "First Assignment"):
		frappe.throw(_("Only tool-access steps and your first assignment can be marked done by you. Your manager handles the rest."))
	if not step["can_mark_done"]:
		frappe.throw(_("This step isn't ready yet ({0}). Finish the steps above it first.").format(step["state"]))

	from my_hr_app.agentroster import mail
	from my_hr_app.agentroster.agent import _get_active_onboarding, set_agent_status

	if step["kind"] == "First Assignment":
		task = frappe.get_doc("Task", emp.first_assignment)
		task.status = "Completed"
		task.flags.from_agentroster = True
		task.save(ignore_permissions=True)
		task.add_comment("Comment", _("Submitted by {0}: {1}").format(emp.employee_name, evidence[:1000]))
		set_agent_status(emp, "Awaiting Approval", save=True)
		mail.comment(emp, _("First assignment submitted: {0}").format(evidence[:1000]))
		mail.send_approval_request(frappe.get_doc("Employee", emp.name))
		frappe.db.commit()
		return _finish()

	doc = frappe.get_doc("Employee Onboarding", _get_active_onboarding(emp.name))
	target = next(r for r in doc.activities if r.name == row)
	target.access_status = "Accepted"
	target.evidence = evidence[:1000]
	doc.flags.from_agentroster = True
	doc.save(ignore_permissions=True)  # fires the status sync (all done -> Ready for Assignment)

	mail.comment(emp, _("{0} marked done: {1} ({2})").format(emp.employee_name, target.agent_tool or target.activity_name, evidence))
	mail.send_manager_notification(emp, _("{0} finished {1}: {2}").format(emp.employee_name, target.agent_tool or target.activity_name, evidence))
	frappe.db.commit()
	return _finish()


def _finish():
	if frappe.form_dict.get("from_page"):
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = PAGE + "?done=1"
		return
	return build_checklist(_my_employee())
