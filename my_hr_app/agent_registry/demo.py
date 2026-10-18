"""Seed Hackathon Labs and walk the agent onboarding demo."""

import json
import urllib.error
import urllib.request

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, today

from my_hr_app.agent_registry.api import agents_over_budget_count, get_budget_summary
from my_hr_app.agent_registry.auth import accept_agent_invite, prevent_agent_self_signup
from my_hr_app.agent_registry.boarding import complete_onboarding_tasks


COMPANY_NAME = "Hackathon Labs"


def run():
	frappe.set_user("Administrator")
	company = ensure_company()
	department = ensure_department(company)
	designation = ensure_designation()
	owner = ensure_owner(company, department, designation)
	holiday_list = ensure_holiday_list(company)

	leave_bot = walk_agent(
		agent_name="Leave Bot",
		company=company,
		department=department,
		designation=designation,
		owner=owner,
		holiday_list=holiday_list,
		monthly_budget=200,
		spend=40,
		deactivate=True,
	)
	recruiting_bot = walk_agent(
		agent_name="Recruiting Bot",
		company=company,
		department=department,
		designation=designation,
		owner=owner,
		holiday_list=holiday_list,
		monthly_budget=100,
		spend=250,
		deactivate=False,
	)

	signup_blocked = assert_signup_blocked()
	summary = get_budget_summary(recruiting_bot["name"])
	over_budget = agents_over_budget_count()
	archived_hidden = frappe.get_all(
		"AI Agent", filters={"status": ["!=", "Archived"], "name": leave_bot["name"]}
	)
	audit_rows = frappe.db.count("Version", {"ref_doctype": "AI Agent", "docname": leave_bot["name"]})

	result = {
		"company": company,
		"owner": owner,
		"leave_bot": leave_bot,
		"recruiting_bot": recruiting_bot,
		"signup_blocked": signup_blocked,
		"recruiting_bot_over_budget": summary["over_budget"],
		"over_budget_count": over_budget["value"],
		"archived_hidden_from_default_list": not archived_hidden,
		"leave_bot_audit_rows": audit_rows,
	}
	print(json.dumps(result, default=str, indent=2))
	frappe.db.commit()
	return result


def walk_agent(
	agent_name, company, department, designation, owner, holiday_list, monthly_budget, spend, deactivate
):
	opening = frappe.get_doc(
		{
			"doctype": "Job Opening",
			"job_title": agent_name,
			"company": company,
			"designation": designation,
			"department": department,
			"status": "Open",
			"worker_kind": "AI Agent",
		}
	).insert(ignore_permissions=True)

	agent = frappe.get_doc(
		{
			"doctype": "AI Agent",
			"agent_name": agent_name,
			"company": company,
			"department": department,
			"designation": designation,
			"owner_employee": owner,
			"job_opening": opening.name,
			"agent_type": "In-house",
			"model_provider": "Anthropic",
			"model_name": "Claude",
			"version": "1.0",
			"execution_mode": "Delegate" if agent_name == "Leave Bot" else "Ambient",
			"risk_tier": "Medium" if agent_name == "Leave Bot" else "High",
			"handles_pii": 1 if agent_name == "Recruiting Bot" else 0,
			"data_region": "US",
			"monthly_budget": monthly_budget,
			"budget_unit": "USD",
			"credential_rotation_due": add_days(today(), -1) if deactivate else add_days(today(), 30),
			"status": "Requested",
			"skills": [
				{
					"skill_name": "Read leave applications" if agent_name == "Leave Bot" else "Screen applicants",
					"allowed_doctype": "Leave Application" if agent_name == "Leave Bot" else "Job Applicant",
					"can_read": 1,
					"can_write": 0,
					"can_create": 0,
				}
			],
			"interaction_policy": [{"role": "HR User", "skill_name": "Read leave applications"}],
		}
	).insert(ignore_permissions=True)

	for action in ("Submit for Review", "Approve"):
		agent = apply_workflow(frappe.get_doc("AI Agent", agent.name), action)

	agent.reload()
	password = "AgentPortal!" + agent.name
	signed_up = accept_agent_invite(agent.invite_key, agent.agent_name, password)
	agent.reload()
	user = frappe.get_doc("User", agent.system_user)
	api_key = signed_up["api_key"]
	api_secret = signed_up["api_secret"]

	login_status = http_status(
		"/api/method/login",
		data={"usr": user.email, "pwd": password},
	)
	api_before = http_status(
		"/api/method/frappe.auth.get_logged_user",
		headers={"Authorization": f"token {api_key}:{api_secret}"},
	)

	submit_governance(agent, company)
	agent = apply_workflow(frappe.get_doc("AI Agent", agent.name), "Start Onboarding")
	complete_onboarding_tasks(agent.name)
	agent.reload()

	frappe.get_doc(
		{
			"doctype": "Agent Usage Log",
			"ai_agent": agent.name,
			"date": today(),
			"calls": 12,
			"tokens": 4000,
			"cost": spend,
			"task_summary": "Demo usage for the registry dashboard",
			"on_behalf_of": "Administrator" if agent.execution_mode == "Delegate" else None,
		}
	).insert(ignore_permissions=True)

	api_after = None
	if deactivate:
		agent = apply_workflow(frappe.get_doc("AI Agent", agent.name), "Deactivate")
		api_after = http_status(
			"/api/method/frappe.auth.get_logged_user",
			headers={"Authorization": f"token {api_key}:{api_secret}"},
		)
		agent = apply_workflow(frappe.get_doc("AI Agent", agent.name), "Archive")

	agent.reload()
	roles = frappe.get_all("Has Role", filters={"parent": agent.system_user, "role": "HR User"})
	return {
		"name": agent.name,
		"status": agent.status,
		"email": agent.agent_email,
		"job_opening": opening.name,
		"holiday_list": holiday_list,
		"login_http_status": login_status,
		"api_before_deactivation": api_before,
		"api_after_deactivation": api_after,
		"access_role_applied": bool(roles),
		"onboarding": frappe.db.get_value(
			"Agent Onboarding", {"ai_agent": agent.name}, ["name", "boarding_status", "project"], as_dict=True
		),
	}


def submit_governance(agent, company):
	agreement = frappe.get_doc(
		{
			"doctype": "Agent Business Agreement",
			"ai_agent": agent.name,
			"accountable_owner": agent.owner_employee,
			"signed_by_owner": 1,
			"approved_by": "Administrator",
			"valid_till": add_days(today(), 365),
			"liability_clause": "The human owner is accountable for this agent's actions.",
			"data_handling_terms": "The agent may only access records granted by its access policy.",
			"vendor_terms": "In-house agent. No third-party vendor terms.",
		}
	)
	agreement.insert(ignore_permissions=True)
	agreement.submit()

	sop = frappe.get_doc(
		{
			"doctype": "Agent SOP",
			"ai_agent": agent.name,
			"purpose": f"Operate {agent.agent_name} within HR policy.",
			"operating_procedure": "Follow the approved skills. Stop and notify the owner on uncertainty.",
			"escalation_path": "Human owner, then HR Manager.",
			"handoff_conditions": "Personal data disputes, exceptions, and anything outside the approved skill.",
			"incident_contact": agent.owner_employee,
		}
	)
	sop.insert(ignore_permissions=True)
	sop.submit()

	policy = frappe.get_doc(
		{
			"doctype": "Agent Access Policy",
			"ai_agent": agent.name,
			"justification": "Least privilege for the agent's declared skills.",
			"approved_by_it": "Administrator",
			"roles": [{"role": "HR User"}],
			"user_permissions": [{"reference_doctype": "Company", "permission_value": company}],
		}
	)
	policy.insert(ignore_permissions=True)
	policy.submit()


def assert_signup_blocked():
	doc = frappe.new_doc("User")
	doc.email = "rogue-agent@hackathonlabs.example"
	doc.first_name = "Rogue"
	doc.user_type = "Agent System User"
	try:
		prevent_agent_self_signup(doc)
		return False
	except frappe.ValidationError:
		pass
	try:
		accept_agent_invite("not-a-real-invite", "Rogue", "longpassword")
	except frappe.ValidationError:
		return True
	return False


def ensure_company():
	if frappe.db.exists("Company", COMPANY_NAME):
		return COMPANY_NAME
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY_NAME,
			"abbr": "HL",
			"default_currency": "USD",
			"country": "United States",
			"email": "hr@hackathonlabs.example",
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def ensure_department(company):
	existing = frappe.db.get_value(
		"Department", {"department_name": "People Operations", "company": company}, "name"
	)
	if existing:
		return existing
	parent = frappe.db.get_value("Department", {"company": company, "is_group": 1}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Department",
			"department_name": "People Operations",
			"company": company,
			"parent_department": parent,
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return doc.name


def ensure_designation():
	if frappe.db.exists("Designation", "Agent Owner"):
		return "Agent Owner"
	frappe.get_doc({"doctype": "Designation", "designation_name": "Agent Owner"}).insert(
		ignore_permissions=True
	)
	return "Agent Owner"


def ensure_owner(company, department, designation):
	existing = frappe.db.get_value("Employee", {"employee_name": "Alex Owner", "company": company}, "name")
	if existing:
		return existing
	gender = frappe.db.get_value("Gender", {}, "name") or "Male"
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Alex",
			"last_name": "Owner",
			"company": company,
			"department": department,
			"designation": designation,
			"date_of_joining": "2026-01-15",
			"date_of_birth": "1992-04-02",
			"gender": gender,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	return employee.name


def ensure_holiday_list(company):
	name = "Hackathon Labs 2026"
	if not frappe.db.exists("Holiday List", name):
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_value("Company", company, "default_holiday_list"):
		frappe.db.set_value("Company", company, "default_holiday_list", name)
	return name


def http_status(path, data=None, headers=None, return_body=False):
	payload = None
	request_headers = {"Accept": "application/json"}
	if headers:
		request_headers.update(headers)
	if data is not None:
		payload = json.dumps(data).encode()
		request_headers["Content-Type"] = "application/json"
	request = urllib.request.Request(f"http://127.0.0.1:8000{path}", data=payload, headers=request_headers)
	try:
		with urllib.request.urlopen(request, timeout=30) as response:
			response_body = response.read().decode()
			if return_body:
				return response.status, response_body
			return response.status
	except urllib.error.HTTPError as exc:
		response_body = exc.read().decode()
		if return_body:
			return exc.code, response_body
		return exc.code
