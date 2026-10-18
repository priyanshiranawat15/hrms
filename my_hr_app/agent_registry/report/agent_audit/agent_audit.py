import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Time", "fieldname": "creation", "fieldtype": "Datetime", "width": 170},
		{"label": "Actor", "fieldname": "actor", "fieldtype": "Data", "width": 200},
		{"label": "Kind", "fieldname": "kind", "fieldtype": "Data", "width": 120},
		{"label": "DocType", "fieldname": "ref_doctype", "fieldtype": "Data", "width": 160},
		{"label": "Document", "fieldname": "document", "fieldtype": "Data", "width": 160},
		{"label": "Detail", "fieldname": "detail", "fieldtype": "Data", "width": 420},
	]

	agent_users = frappe.get_all("AI Agent", filters={"system_user": ["is", "set"]}, pluck="system_user")
	agent_filter = filters.get("ai_agent")
	version_filters = {"ref_doctype": "AI Agent"}
	if agent_filter:
		version_filters["docname"] = agent_filter

	rows = []
	for version in frappe.get_all(
		"Version",
		filters=version_filters,
		fields=["creation", "owner", "ref_doctype", "docname", "data"],
		order_by="creation desc",
		limit=100,
	):
		rows.append(
			{
				"creation": version.creation,
				"actor": version.owner,
				"kind": "Document change",
				"ref_doctype": version.ref_doctype,
				"document": version.docname,
				"detail": version.data,
			}
		)

	activity_filters = {}
	if agent_users:
		activity_filters["user"] = ["in", agent_users]
	if agent_filter:
		activity_filters["reference_name"] = agent_filter
	if activity_filters.get("user") or agent_filter:
		for activity in frappe.get_all(
			"Activity Log",
			filters=activity_filters,
			fields=["creation", "user", "subject", "reference_doctype", "reference_name", "operation"],
			order_by="creation desc",
			limit=100,
		):
			rows.append(
				{
					"creation": activity.creation,
					"actor": activity.user,
					"kind": activity.operation or "Activity",
					"ref_doctype": activity.reference_doctype,
					"document": activity.reference_name,
					"detail": activity.subject,
				}
			)

	rows.sort(key=lambda row: str(row["creation"]), reverse=True)
	return columns, rows
