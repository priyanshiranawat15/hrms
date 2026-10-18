import frappe
from frappe import _
from frappe.utils import flt


def sync_from_project(doc, method=None):
	_sync_project(doc.name, flt(doc.percent_complete))


def sync_from_task(doc, method=None):
	if not doc.project or doc.flags.get("from_project"):
		return
	_sync_project(doc.project, None)


def _sync_project(project_name, percent):
	onboarding = frappe.db.get_value(
		"Agent Onboarding", {"project": project_name, "docstatus": 1}, "name"
	)
	if not onboarding:
		return

	if percent is None:
		tasks = frappe.get_all("Task", filters={"project": project_name}, fields=["status"])
		if not tasks:
			percent = 0
		else:
			done = sum(1 for task in tasks if task.status == "Completed")
			percent = done / len(tasks) * 100

	status = "Pending"
	if 0 < percent < 100:
		status = "In Process"
	elif percent >= 100:
		status = "Completed"

	frappe.db.set_value("Agent Onboarding", onboarding, "boarding_status", status)
	if status == "Completed":
		agent = frappe.db.get_value("Agent Onboarding", onboarding, "ai_agent")
		try_activate(agent)


def try_activate(agent_name):
	"""Move an agent to Active once agreements, access, and onboarding are done."""
	if not agent_name:
		return
	agent = frappe.get_doc("AI Agent", agent_name)
	if agent.status != "Onboarding":
		return
	missing = agent.activation_blockers()
	if missing:
		return
	agent.db_set("status", "Active")
	if not agent.activation_date:
		agent.db_set("activation_date", frappe.utils.today())
	frappe.msgprint(
		_("Agent {0} is now Active.").format(agent.agent_name),
		alert=True,
		indicator="green",
	)


@frappe.whitelist()
def complete_onboarding_tasks(agent):
	"""Mark every onboarding task complete. Used by the demo and by owners finishing a checklist."""
	frappe.has_permission("Agent Onboarding", "write", throw=True)
	onboarding = frappe.db.get_value(
		"Agent Onboarding", {"ai_agent": agent, "docstatus": 1}, ["name", "project"], as_dict=True
	)
	if not onboarding:
		frappe.throw(_("Submit an Agent Onboarding for this agent first."))

	for task_name in frappe.get_all("Task", filters={"project": onboarding.project}, pluck="name"):
		task = frappe.get_doc("Task", task_name)
		if task.status != "Completed":
			task.status = "Completed"
			task.save(ignore_permissions=True)

	_sync_project(onboarding.project, 100)
	return frappe.db.get_value("AI Agent", agent, "status")
