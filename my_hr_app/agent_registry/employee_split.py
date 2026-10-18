"""Agents are Employees. Human-only HR sections stay closed to them."""

import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import cint

AGENT_ROLE = "Agent Worker"
ROLE_PROFILE = "Agent Worker"

SKIPPED_DOCTYPES = (
	"Job Opening",
	"Job Applicant",
	"Job Offer",
	"Interview",
	"Appointment Letter",
	"Salary Structure",
	"Salary Structure Assignment",
	"Salary Slip",
	"Payroll Entry",
	"Income Tax Slab",
	"Employee Tax Exemption Declaration",
	"Employee Tax Exemption Proof Submission",
	"Gratuity",
	"Gratuity Rule",
	"Employee Incentive",
	"Retention Bonus",
	"Leave Application",
	"Leave Allocation",
	"Leave Policy",
	"Leave Policy Assignment",
	"Leave Encashment",
	"Compensatory Leave Request",
	"Attendance",
	"Employee Checkin",
	"Shift Type",
	"Shift Assignment",
	"Shift Schedule Assignment",
	"Attendance Request",
	"Travel Request",
	"Expense Claim",
	"Employee Advance",
	"Employee Benefit Application",
	"Employee Benefit Claim",
	"Loan",
	"Employee Grievance",
	"Training Program",
	"Training Event",
	"Training Result",
	"Training Feedback",
)

PERSONAL_FIELDS = (
	"gender",
	"date_of_birth",
	"salutation",
	"marital_status",
	"blood_group",
	"family_background",
	"health_details",
	"personal_email",
	"prefered_contact_email",
	"bank_name",
	"bank_ac_no",
	"iban",
	"salary_mode",
	"passport_number",
	"date_of_issue",
	"valid_upto",
	"place_of_issue",
	"current_address",
	"permanent_address",
	"current_accommodation_type",
	"permanent_accommodation_type",
	"person_to_be_contacted",
	"relation",
	"emergency_phone_number",
)

ONBOARDING_ACTIVITIES = (
	"Connect",
	"Get access",
	"Load context",
	"Pass the test run",
	"Manager approval",
)

OFFBOARDING_ACTIVITIES = (
	"Revoke tokens",
	"Withdraw context",
	"Archive the activity log",
	"Set status to Left",
)


def ensure_employee_split():
	ensure_employee_fields()
	relax_personal_requirements()
	ensure_agent_role()
	ensure_agent_permissions()
	ensure_boarding_template("Employee Onboarding Template", "Agent Onboarding", ONBOARDING_ACTIVITIES)
	ensure_boarding_template("Employee Separation Template", "Agent Offboarding", OFFBOARDING_ACTIVITIES)


def ensure_employee_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "worker_type",
					"label": "Worker Type",
					"fieldtype": "Select",
					"options": "Human\nAgent",
					"default": "Human",
					"insert_after": "status",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "agent_profile",
					"label": "Agent Profile",
					"fieldtype": "Link",
					"options": "AI Agent",
					"insert_after": "worker_type",
					"depends_on": "eval:doc.worker_type=='Agent'",
					"description": "Details of the model, vendor, and skills.",
				},
				{
					"fieldname": "operator",
					"label": "Operator",
					"fieldtype": "Data",
					"insert_after": "agent_profile",
					"depends_on": "eval:doc.worker_type=='Agent'",
					"description": "Company or person running this agent.",
				},
			]
		}
	)


def relax_personal_requirements():
	"""Gender and date of birth are required for people. Agents leave them empty."""
	for fieldname in ("gender", "date_of_birth"):
		make_property_setter("Employee", fieldname, "reqd", "0", "Check", validate_fields_for_doctype=False)


def ensure_agent_role():
	if frappe.db.exists("Role", AGENT_ROLE):
		frappe.db.set_value("Role", AGENT_ROLE, "desk_access", 1)
	else:
		frappe.get_doc(
			{"doctype": "Role", "role_name": AGENT_ROLE, "desk_access": 1, "is_custom": 1}
		).insert(ignore_permissions=True)

	if frappe.db.exists("Role Profile", ROLE_PROFILE):
		return
	frappe.get_doc(
		{
			"doctype": "Role Profile",
			"role_profile": ROLE_PROFILE,
			"roles": [{"role": AGENT_ROLE}],
		}
	).insert(ignore_permissions=True)


def ensure_agent_permissions():
	grants = {
		"Employee": {"read": 1},
		"Task": {"read": 1, "write": 1, "create": 1},
		"ToDo": {"read": 1, "write": 1, "create": 1},
		"Employee Onboarding": {"read": 1},
		"Employee Separation": {"read": 1},
		"Comment": {"read": 1, "write": 1, "create": 1},
	}
	for doctype, rights in grants.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": AGENT_ROLE, "permlevel": 0}):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": AGENT_ROLE,
				"permlevel": 0,
				"select": 1,
				**rights,
			}
		).insert(ignore_permissions=True)


def ensure_boarding_template(doctype, title, activities):
	if not frappe.db.exists("DocType", doctype):
		return
	if frappe.db.exists(doctype, {"title": title}):
		return
	doc = frappe.get_doc({"doctype": doctype, "title": title})
	for offset, activity_name in enumerate(activities):
		doc.append(
			"activities",
			{
				"activity_name": activity_name,
				"role": "HR Manager",
				"begin_on": offset,
				"duration": 1,
				"task_weight": 20,
			},
		)
	doc.insert(ignore_permissions=True)


def validate_employee(doc, method=None):
	if (doc.worker_type or "Human") == "Agent":
		return
	missing = []
	if not doc.gender:
		missing.append(_("Gender"))
	if not doc.date_of_birth:
		missing.append(_("Date of Birth"))
	if missing:
		frappe.throw(_("Human employees require {0}.").format(", ".join(missing)))


def on_employee_update(doc, method=None):
	if doc.worker_type != "Agent":
		return
	previous = doc.get_doc_before_save()
	joined = not previous or previous.worker_type != "Agent"
	if joined and doc.user_id:
		notify_managers(doc, _("{0} joined as an AI coworker").format(doc.employee_name))
	elif previous and previous.status != "Left" and doc.status == "Left":
		notify_managers(doc, _("{0} was offboarded").format(doc.employee_name))


def ensure_agent_employee(agent, user):
	"""A short workforce row, created when the agent accepts the invite."""
	existing = frappe.db.get_value("Employee", {"agent_profile": agent.name}, "name")
	if not existing and user:
		existing = frappe.db.get_value("Employee", {"user_id": user.name}, "name")
	if existing:
		employee = frappe.get_doc("Employee", existing)
		updates = {}
		if user and employee.user_id != user.name:
			updates["user_id"] = user.name
		if agent.agent_email and employee.company_email != agent.agent_email:
			updates["company_email"] = agent.agent_email
		if employee.worker_type != "Agent":
			updates["worker_type"] = "Agent"
		if not employee.agent_profile:
			updates["agent_profile"] = agent.name
		if updates:
			employee.db_set(updates)
		return employee

	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"naming_series": "HR-EMP-",
			"first_name": agent.agent_name,
			"company": agent.company,
			"department": agent.department,
			"designation": agent.designation,
			"reports_to": agent.owner_employee,
			"status": "Active",
			"date_of_joining": frappe.utils.today(),
			"worker_type": "Agent",
			"agent_profile": agent.name,
			"user_id": user.name if user else None,
			"company_email": agent.agent_email,
			"create_user_automatically": 0,
		}
	)
	employee.flags.ignore_permissions = True
	employee.insert(ignore_permissions=True)
	return employee


def block_skipped_document(doc, method=None):
	if _session_is_agent():
		frappe.throw(
			_("{0} is hidden from agent users. An agent does not use recruitment, pay, leave, attendance, expenses, or benefits.").format(
				doc.doctype
			)
		)
	for employee in _linked_employees(doc):
		if _is_agent_employee(employee):
			frappe.throw(
				_("{0} stays empty for {1}. That employee is an AI coworker.").format(doc.doctype, employee)
			)


def get_children(parent=None, company=None, exclude_node=None):
	from hrms.hr.page.organizational_chart.organizational_chart import get_children as original

	rows = original(parent=parent, company=company, exclude_node=exclude_node)
	if not rows or not frappe.get_meta("Employee").has_field("worker_type"):
		return rows
	types = {
		row.name: row.worker_type
		for row in frappe.get_all(
			"Employee",
			filters={"name": ["in", [row.id for row in rows]]},
			fields=["name", "worker_type"],
		)
	}
	for row in rows:
		if types.get(row.id) == "Agent":
			row.title = f"AI · {row.title}" if row.title else "AI"
	return rows


def _grant_scope(user, employee):
	scopes = [("Employee", employee.name), ("Company", employee.company), ("Department", employee.department)]
	for allow, value in scopes:
		if not value or not frappe.db.exists("DocType", allow):
			continue
		if frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": value}):
			continue
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": allow, "for_value": value}
		).insert(ignore_permissions=True)


def _session_is_agent():
	user = frappe.session.user
	if user in ("Administrator", "Guest"):
		return False
	if AGENT_ROLE in frappe.get_roles(user):
		return True
	if not frappe.get_meta("Employee").has_field("worker_type"):
		return False
	return cint(
		frappe.db.get_value("Employee", {"user_id": user, "worker_type": "Agent"}, "name") is not None
	)


def _is_agent_employee(employee):
	if not employee or not frappe.get_meta("Employee").has_field("worker_type"):
		return False
	return frappe.db.get_value("Employee", employee, "worker_type") == "Agent"


def _linked_employees(doc):
	found = []
	for field in ("employee", "employee_id"):
		if doc.get(field):
			found.append(doc.get(field))
	return found


def notify_managers(employee, subject):
	recipients = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		pluck="parent",
	)
	emails = []
	for user in recipients:
		email = frappe.db.get_value("User", user, "email")
		if email and email not in emails:
			emails.append(email)
	if not emails:
		return
	try:
		frappe.sendmail(
			recipients=emails,
			subject=subject,
			message=_("{0} ({1}), department {2}.").format(
				employee.employee_name, employee.name, employee.department or "-"
			),
		)
	except Exception:
		pass
