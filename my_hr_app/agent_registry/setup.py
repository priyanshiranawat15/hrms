import frappe

TEMPLATE_TITLE = "Standard Agent Onboarding"
WORKFLOW_NAME = "AI Agent Lifecycle"
AGENT_USER_TYPE = "Agent System User"

ACTIVITIES = [
	{"activity_name": "Sign business agreement", "required_for_employee_creation": 1, "begin_on": 0, "duration": 1, "task_weight": 20},
	{"activity_name": "Publish SOP", "required_for_employee_creation": 1, "begin_on": 0, "duration": 1, "task_weight": 15},
	{"activity_name": "IT security review", "required_for_employee_creation": 1, "begin_on": 1, "duration": 2, "task_weight": 20},
	{"activity_name": "Sandbox evaluation", "required_for_employee_creation": 0, "begin_on": 1, "duration": 2, "task_weight": 15},
	{"activity_name": "Provision credentials", "required_for_employee_creation": 1, "begin_on": 2, "duration": 1, "task_weight": 20},
	{"activity_name": "Owner acknowledgement", "required_for_employee_creation": 1, "begin_on": 3, "duration": 1, "task_weight": 10},
]

WORKFLOW_STATES = [
	("Requested", "Warning"),
	("Under Review", "Info"),
	("Approved", "Primary"),
	("Onboarding", "Warning"),
	("Active", "Success"),
	("Deactivated", "Danger"),
	("Archived", "Inverse"),
	("Rejected", "Danger"),
]

WORKFLOW_TRANSITIONS = [
	("Requested", "Submit for Review", "Under Review", "HR User"),
	("Under Review", "Approve", "Approved", "HR Manager"),
	("Under Review", "Reject", "Rejected", "HR Manager"),
	("Approved", "Start Onboarding", "Onboarding", "HR User"),
	("Onboarding", "Activate", "Active", "HR Manager"),
	("Active", "Deactivate", "Deactivated", "HR Manager"),
	("Deactivated", "Reactivate", "Active", "HR Manager"),
	("Deactivated", "Archive", "Archived", "HR Manager"),
	("Active", "Archive", "Archived", "System Manager"),
	("Rejected", "Reopen", "Requested", "HR User"),
]


def ensure_agent_registry():
	ensure_agent_user_type()
	ensure_custom_fields()
	ensure_onboarding_template()
	ensure_workflow()
	ensure_hiring_links()
	frappe.clear_cache()


def ensure_agent_user_type():
	if not frappe.db.exists("Role", AGENT_USER_TYPE):
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": AGENT_USER_TYPE,
				"desk_access": 1,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Role", AGENT_USER_TYPE, "desk_access", 1)

	data = {
		"role": AGENT_USER_TYPE,
		"apply_user_permission_on": "AI Agent",
		"user_id_field": "system_user",
		"doctypes": {
			"AI Agent": ["read"],
			"Agent Business Agreement": ["read"],
			"Agent SOP": ["read"],
			"Agent Access Policy": ["read"],
			"Agent Onboarding": ["read"],
			"Agent Usage Log": ["read", "write", "create"],
			"Company": ["read"],
		},
	}
	if frappe.db.exists("User Type", AGENT_USER_TYPE):
		doc = frappe.get_doc("User Type", AGENT_USER_TYPE)
		doc.user_doctypes = []
	else:
		doc = frappe.new_doc("User Type")
		doc.update(
			{
				"name": AGENT_USER_TYPE,
				"role": data["role"],
				"user_id_field": data["user_id_field"],
				"apply_user_permission_on": data["apply_user_permission_on"],
			}
		)

	for doctype, permissions in data["doctypes"].items():
		row = {"document_type": doctype}
		for permission in permissions:
			row[permission] = 1
		doc.append("user_doctypes", row)

	if hasattr(doc, "user_type_modules"):
		doc.user_type_modules = []
		doc.append("user_type_modules", {"module": "Agent Registry"})

	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)


def ensure_custom_fields():
	if frappe.db.exists("Custom Field", {"dt": "Job Opening", "fieldname": "worker_kind"}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Job Opening",
			"fieldname": "worker_kind",
			"label": "Worker Kind",
			"fieldtype": "Select",
			"options": "Human\nAI Agent",
			"insert_after": "designation",
			"default": "Human",
			"in_standard_filter": 1,
			"in_list_view": 1,
			"description": "Human openings follow recruitment. AI Agent openings are registered in the Agent Registry.",
		}
	).insert(ignore_permissions=True)


def ensure_onboarding_template():
	if frappe.db.exists("Agent Onboarding Template", TEMPLATE_TITLE):
		return
	template = frappe.get_doc(
		{
			"doctype": "Agent Onboarding Template",
			"title": TEMPLATE_TITLE,
		}
	)
	for activity in ACTIVITIES:
		template.append("activities", {"role": "HR Manager", **activity})
	template.insert(ignore_permissions=True)


def ensure_workflow():
	for state, style in WORKFLOW_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	actions = {row[1] for row in WORKFLOW_TRANSITIONS}
	for action in actions:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.delete_doc("Workflow", WORKFLOW_NAME, force=1, ignore_permissions=True)

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW_NAME,
			"document_type": "AI Agent",
			"is_active": 1,
			"send_email_alert": 0,
			"workflow_state_field": "status",
			"override_status": 0,
		}
	)
	for state, _style in WORKFLOW_STATES:
		workflow.append(
			"states",
			{
				"state": state,
				"doc_status": "0",
				"allow_edit": "HR Manager",
			},
		)
	for state, action, next_state, allowed in WORKFLOW_TRANSITIONS:
		workflow.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": allowed,
				"allow_self_approval": 1,
			},
		)
	workflow.insert(ignore_permissions=True)


def ensure_hiring_links():
	"""Keep agents next to employees in HR Setup and Recruitment, not as a separate app."""
	if frappe.db.exists("Workspace", "Agent Registry"):
		frappe.db.set_value("Workspace", "Agent Registry", "is_hidden", 1)

	insert_sidebar_link("HR Setup", "Employee", "AI Agent", "AI Agent", "bot")
	insert_sidebar_link("HR Setup", "AI Agent", "Agent Onboarding", "Agent Onboarding", "list-checks")
	insert_sidebar_link("Recruitment", "Job Offer", "AI Agent", "AI Agent", "bot")


def insert_sidebar_link(sidebar_name, after_label, label, link_to, icon):
	if not frappe.db.exists("Sidebar", sidebar_name):
		return
	sidebar = frappe.get_doc("Sidebar", sidebar_name)
	if any(row.label == label and row.link_to == link_to for row in sidebar.items):
		return

	items = []
	inserted = False
	for row in sidebar.items:
		items.append(row.as_dict())
		if row.label == after_label and not inserted:
			items.append(_sidebar_link(label, link_to, icon))
			inserted = True
	if not inserted:
		items.append(_sidebar_link(label, link_to, icon))

	sidebar.items = []
	for item in items:
		sidebar.append(
			"items",
			{
				"type": item.get("type") or "Link",
				"label": item.get("label"),
				"link_type": item.get("link_type"),
				"link_to": item.get("link_to"),
				"icon": item.get("icon"),
				"child": item.get("child") or 0,
				"collapsible": item.get("collapsible", 1),
				"indent": item.get("indent") or 0,
				"keep_closed": item.get("keep_closed") or 0,
				"open_in_new_tab": item.get("open_in_new_tab") or 0,
				"show_arrow": item.get("show_arrow") or 0,
				"url": item.get("url"),
				"navigate_to_tab": item.get("navigate_to_tab"),
				"filters": item.get("filters"),
				"route_options": item.get("route_options"),
			},
		)
	sidebar.flags.ignore_links = True
	sidebar.save(ignore_permissions=True)


def _sidebar_link(label, link_to, icon):
	return {
		"type": "Link",
		"label": label,
		"link_type": "DocType",
		"link_to": link_to,
		"icon": icon,
		"child": 0,
		"collapsible": 1,
		"indent": 0,
		"keep_closed": 0,
		"open_in_new_tab": 0,
		"show_arrow": 0,
	}
