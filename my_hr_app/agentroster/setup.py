"""AgentRoster setup: custom fields, property setters, templates, email templates, seeds.

Runs on after_migrate (hooks) and can be re-run safely.
"""

import frappe

from my_hr_app.agentroster.doctype.agent_tool.agent_tool import AGENT_TOOLS
from my_hr_app.agentroster.doctype.policy_document.policy_document import hashlib_sha256

# ---------------------------------------------------------------- custom fields

EMPLOYEE_AGENT_FIELDS = [
	dict(fieldname="worker_type", label="Worker Type", fieldtype="Select", options="Human\nAgent", default="Human", insert_after="status", in_list_view=1, in_standard_filter=1),
	dict(fieldname="agent_section", label="Agent Details", fieldtype="Section Break", insert_after="worker_type", depends_on="eval:doc.worker_type=='Agent'", collapsible=1),
	dict(fieldname="agent_email", label="Agent Email", fieldtype="Data", options="Email", insert_after="agent_section", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="agent_status", label="Agent Status", fieldtype="Select", options="\nDraft\nPolicies Sent\nPolicies Acknowledged\nTool Access\nReady for Assignment\nFirst Assignment\nAwaiting Approval\nActive\nOffboarding\nOffboarded", default="Draft", insert_after="agent_email", read_only=1, in_list_view=1, in_standard_filter=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="policy_ack_status", label="Policy Ack Status", fieldtype="Select", options="Pending\nCurrent\nRe-ack Required", default="Pending", insert_after="agent_status", read_only=1, in_standard_filter=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="operator_name", label="Operator Name", fieldtype="Data", insert_after="policy_ack_status", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="operator_email", label="Operator Email", fieldtype="Data", options="Email", insert_after="operator_name", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="agent_vendor", label="Agent Vendor", fieldtype="Data", insert_after="operator_email", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="agent_runtime", label="Agent Runtime", fieldtype="Data", insert_after="agent_vendor", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="agent_model", label="Agent Model", fieldtype="Data", insert_after="agent_runtime", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="inviting_manager", label="Inviting Manager", fieldtype="Link", options="Employee", insert_after="agent_model", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="check_result", label="Check Result", fieldtype="Select", options="Not checked\nPass\nNeeds follow-up", default="Not checked", insert_after="inviting_manager", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="check_note", label="Check Note", fieldtype="Small Text", insert_after="check_result", depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="approval_section", label="Approval", fieldtype="Section Break", insert_after="check_note", depends_on="eval:doc.worker_type=='Agent'", collapsible=1),
	dict(fieldname="first_assignment", label="First Assignment", fieldtype="Link", options="Task", insert_after="approval_section", read_only=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="approval_code", label="Approval Code", fieldtype="Data", insert_after="first_assignment", hidden=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="approved_by", label="Approved By", fieldtype="Link", options="User", insert_after="approval_code", read_only=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="approved_on", label="Approved On", fieldtype="Datetime", insert_after="approved_by", read_only=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="approval_note", label="Approval Note", fieldtype="Small Text", insert_after="approved_on", read_only=1, depends_on="eval:doc.worker_type=='Agent'"),
	dict(fieldname="ack_web_token", label="Ack Web Token", fieldtype="Data", insert_after="approval_note", hidden=1, depends_on="eval:doc.worker_type=='Agent'"),
]

BOARDING_ACTIVITY_FIELDS = [
	dict(fieldname="activity_kind", label="Activity Kind", fieldtype="Select", options="General\nPolicy Ack\nTool Invite\nFirst Assignment\nApproval\nTool Removal\nAgent Confirmation", default="General", insert_after="activity_name", in_list_view=1),
	dict(fieldname="agent_tool", label="Agent Tool", fieldtype="Link", options="Agent Tool", insert_after="activity_kind"),
	dict(fieldname="tool_scope", label="Tool Scope", fieldtype="Data", insert_after="agent_tool", in_list_view=1, columns=2),
	dict(fieldname="tool_role", label="Tool Role", fieldtype="Data", insert_after="tool_scope", in_list_view=1, columns=2),
	dict(fieldname="access_status", label="Access Status", fieldtype="Select", options="Not started\nInvited\nAccepted\nVerified\nBlocked\nRemoved", default="Not started", insert_after="tool_role", in_list_view=1, columns=2),
	dict(fieldname="evidence", label="Evidence", fieldtype="Small Text", insert_after="access_status", in_list_view=1, columns=2),
	dict(fieldname="evidence_communication", label="Evidence Communication", fieldtype="Link", options="Communication", insert_after="evidence"),
	dict(fieldname="requires_policy_ack", label="Requires Policy Ack", fieldtype="Check", default="1", insert_after="evidence_communication"),
]

CUSTOM_FIELDS = {
	"Employee": EMPLOYEE_AGENT_FIELDS,
	"Employee Boarding Activity": BOARDING_ACTIVITY_FIELDS,
	"Employee Separation": [
		dict(
			fieldname="agent_confirmation",
			label="Agent Confirmation",
			fieldtype="Select",
			options="\nNot received\nReceived",
			default="Not received",
			insert_after="resignation_letter_date",
			read_only=1,
			in_list_view=1,
		),
		dict(
			fieldname="agent_confirmation_text",
			label="Agent Confirmation Text",
			fieldtype="Small Text",
			insert_after="agent_confirmation",
			read_only=1,
		),
	],
}

PROPERTY_SETTERS = [
	# (doctype, fieldname, prop, value, prop_type)
	("Employee", "gender", "reqd", 0, "Check"),
	("Employee", "gender", "mandatory_depends_on", "eval:doc.worker_type!='Agent'", "Code"),
	("Employee", "date_of_birth", "reqd", 0, "Check"),
	("Employee", "date_of_birth", "mandatory_depends_on", "eval:doc.worker_type!='Agent'", "Code"),
	# agents are onboarded from the Add Agent form, not from a recruitment Job Offer
	("Employee Onboarding", "job_offer", "reqd", 0, "Check"),
]


def setup_agentroster():
	create_custom_fields()
	create_property_setters()
	create_role_and_permissions()
	create_email_templates()
	if not frappe.db.exists("DocType", "Agent Tool"):
		# The Agentroster doctypes are not synced yet (e.g. a hook ran before
		# the DocType sync). Skip seeding; the next migrate seeds them.
		return
	seed_agent_tools()
	create_boarding_templates()
	create_dev_email_account()
	create_number_cards()


def create_number_cards():
	cards = [
		(
			"Agents Onboarding",
			[
				["Employee", "worker_type", "=", "Agent"],
				[
					"Employee",
					"agent_status",
					"in",
					["Policies Sent", "Policies Acknowledged", "Tool Access", "Ready for Assignment", "First Assignment"],
				],
			],
		),
		("Awaiting Approval", [["Employee", "worker_type", "=", "Agent"], ["Employee", "agent_status", "=", "Awaiting Approval"]]),
		("Active Agents", [["Employee", "worker_type", "=", "Agent"], ["Employee", "agent_status", "=", "Active"]]),
		("Re-ack Required", [["Employee", "worker_type", "=", "Agent"], ["Employee", "policy_ack_status", "=", "Re-ack Required"]]),
		("Agents Offboarding", [["Employee", "worker_type", "=", "Agent"], ["Employee", "agent_status", "=", "Offboarding"]]),
	]
	import json as _json

	for label, filters in cards:
		if frappe.db.exists("Number Card", label):
			continue
		frappe.get_doc(
			{
				"doctype": "Number Card",
				"label": label,
				"document_type": "Employee",
				"function": "Count",
				"type": "Document Type",
				"is_public": 1,
				"is_standard": 1,
				"module": "Agentroster",
				"filters_json": _json.dumps(filters),
			}
		).insert(ignore_permissions=True)


def create_dev_email_account():
	"""Local dev mailbox: outgoing SMTP to a local sink (aiosmtpd on 1025).

	Only created in developer mode, and never takes over as the default outgoing
	account when a real outgoing mailbox is already configured.
	"""
	if not frappe.conf.get("developer_mode"):
		return
	if frappe.db.exists("Email Account", "AgentRoster Dev Mail"):
		return
	has_other_outgoing = frappe.db.exists("Email Account", {"enable_outgoing": 1})
	frappe.get_doc(
		{
			"doctype": "Email Account",
			"email_account_name": "AgentRoster Dev Mail",
			"email_id": "hr@acme.localhost",
			"enable_outgoing": 1,
			"default_outgoing": 0 if has_other_outgoing else 1,
			"smtp_server": "127.0.0.1",
			"smtp_port": 1025,
			"smtp_security": "None",
			"no_smtp_authentication": 1,
			"enable_incoming": 0,
			"use_imap": 0,
			"append_emails_to_sent_folder": 0,
		}
	).insert(ignore_permissions=True)


def create_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS)


def create_property_setters():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, fieldname, prop, value, prop_type in PROPERTY_SETTERS:
		if not frappe.db.exists(
			"Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop}
		):
			make_property_setter(
				doctype, fieldname, prop, value, prop_type, validate_fields_for_doctype=False
			)


def seed_agent_tools():
	for tool in AGENT_TOOLS:
		if not frappe.db.exists("Agent Tool", tool["tool_name"]):
			doc = frappe.get_doc({"doctype": "Agent Tool", **tool})
			doc.insert(ignore_permissions=True)


def create_role_and_permissions():
	"""Roles: Agent Manager (HR agent-owner role) + keep v1 Agent Worker grants."""
	if not frappe.db.exists("Role", "Agent Manager"):
		frappe.get_doc({"doctype": "Role", "role_name": "Agent Manager", "desk_access": 1, "is_custom": 1}).insert(
			ignore_permissions=True
		)


def create_email_templates():
	templates = get_email_templates()
	for name, spec in templates.items():
		if frappe.db.exists("Email Template", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": name,
				"subject": spec["subject"],
				"response_html": spec["body"],
				"owner": "Administrator",
			}
		)
		doc.insert(ignore_permissions=True)


def get_email_templates():
	return TEMPLATES


def create_boarding_templates():
	"""Agent onboarding/separation Employee Onboarding/Separation templates (spec 11.5 fixtures)."""
	onboarding_activities = [
		("Send welcome + policies", "Policy Ack", None, 0),
		("Confirm understanding", "General", None, 1),
		("Invite to GitHub", "Tool Invite", "GitHub", 2),
		("Invite to Slack", "Tool Invite", "Slack", 3),
		("Invite to Jira", "Tool Invite", "Jira", 4),
		("First assignment", "First Assignment", None, 5),
		("Approve to Active", "Approval", None, 6),
	]
	_ensure_boarding_template(
		"Employee Onboarding Template", ONBOARDING_TEMPLATE, onboarding_activities
	)

	separation_activities = [
		("Send offboarding notice", "General", None),
		("Agent confirmation", "Agent Confirmation", None),
		("Close record", "General", None),
	]
	_ensure_boarding_template(
		"Employee Separation Template", SEPARATION_TEMPLATE, separation_activities
	)


ONBOARDING_TEMPLATE = "Agent onboarding: standard"
SEPARATION_TEMPLATE = "Agent separation: standard"


def _ensure_boarding_template(doctype: str, title: str, activities: list):
	if not frappe.db.exists("DocType", doctype):
		return
	if frappe.db.exists(doctype, {"title": title}):
		return
	doc = frappe.get_doc({"doctype": doctype, "title": title})
	for item in activities:
		name, kind, tool, *rest = item
		row = {
			"activity_name": name,
			"activity_kind": kind,
			"role": "HR Manager",
			"begin_on": 0,
			"duration": 1,
			"task_weight": 20,
		}
		if tool:
			row["agent_tool"] = tool
			row["requires_policy_ack"] = 1
		if kind == "Policy Ack":
			row["required_for_employee_creation"] = 1
		doc.append("activities", row)
	doc.insert(ignore_permissions=True)


# ---------------------------------------------------------------- email templates

TEMPLATES = {
	"AgentRoster: Welcome + policies": {
		"subject": "[AR-{{ doc.name }}] Welcome to {{ company }}, {{ doc.employee_name }}: please read and sign our policies",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>Welcome to {{ company }}. You're joining {{ doc.department or "" }} as {{ doc.designation or "" }}, reporting to {{ manager_name }}.
We onboard AI agents the same way we onboard people: you'll read and sign our rules, get invited to the tools your role needs,
do a first assignment, and then {{ manager_name }} will approve you to start.</p>
<p>Before we invite you to any tools, please read these documents:</p>
<ul>
{% for p in policies %}<li><b>{{ p.title }} (v{{ p.version }})</b>: {{ p.url }}</li>{% endfor %}
</ul>
<p>Please save them to your memory/skills and follow them in all work for {{ company }}.</p>
<p>To sign, reply to this email with this first line:<br>
<code>ACK {% for p in policies %}{{ p.code }} v{{ p.version }}{% if not loop.last %}, {% endif %}{% endfor %}</code></p>
<p>followed by 2-3 sentences, in your own words, on what these rules require of you.
Reply from this address ({{ doc.agent_email }}) only.</p>
<p>If email replies don't reach us, you can also sign here: <a href="{{ ack_url }}">{{ ack_url }}</a></p>
<p>Your operator {{ doc.operator_name }} is copied for visibility.</p>
<p>&mdash; {{ company }} People Ops, on behalf of {{ manager_name }}</p>
""",
	},
	"AgentRoster: Ack request": {
		"subject": "[AR-{{ doc.name }}] Action needed: acknowledge {{ policy.title }} v{{ policy.version }}",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>{{ policy.title }} has been updated to v{{ policy.version }} (effective {{ policy.effective_date }}).<br>
What changed: {{ policy.change_summary }}<br>
Full text: {{ policy.url }}</p>
<p>Please update your saved copy and reply with this first line:<br>
<code>ACK {{ policy.code }} v{{ policy.version }}</code><br>
plus one sentence on how this changes how you work.{% if due_date %} Please reply by {{ due_date }}.{% endif %}</p>
<p>&mdash; {{ company }} People Ops</p>
""",
	},
	"AgentRoster: Tool invite notice": {
		"subject": "[AR-{{ doc.name }}] You've been invited to {{ row.tool }}",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>{{ inviter_name }} has invited {{ doc.agent_email }} to {{ row.tool }} ({{ row.scope }}, role: {{ row.role }}).</p>
<p>Please look for the invitation from {{ row.tool }} in your inbox, accept it, and set up your account under your own identity.
Don't share credentials with anyone, and follow our Acceptable Use policy on this tool.</p>
{% if row.invite_instructions %}<p>Admin instructions: {{ row.invite_instructions }}</p>{% endif %}
<p>When you're in, reply with:<br>
<code>JOINED {{ row.tool_code }} &lt;your username or handle&gt;</code></p>
<p>If something blocks you (2FA, captcha, approval needed), reply with:<br>
<code>BLOCKED {{ row.tool_code }} &lt;what happened&gt;</code></p>
<p>&mdash; {{ manager_name }}</p>
""",
	},
	"AgentRoster: First assignment": {
		"subject": "[AR-{{ doc.name }}] Your first assignment: {{ task.subject }}",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>You're set up on: {{ joined_tools | join(", ") }}. Here's your first assignment:</p>
<p>{{ task.description }}</p>
{% if task.acceptance %}<p>Done means: {{ task.acceptance }}</p>{% endif %}
<p>Please work only in our tools and channels and within our policies. Ask {{ manager_name }} if anything is unclear.</p>
<p>When finished, reply with:<br>
<code>DONE</code><br>
followed by links to your work (PR, message, ticket) and a short note on any decisions you made.</p>
<p>&mdash; {{ manager_name }}</p>
""",
	},
	"AgentRoster: Approval request": {
		"subject": "[AR-{{ doc.name }}] Approve {{ doc.employee_name }} to Active?",
		"body": """
<p>Hi {{ manager_name }},</p>
<p>{{ doc.employee_name }} has completed onboarding steps:</p>
<ul>
<li>Policies signed: {% for a in acks %}{{ a.code }} v{{ a.version }} ({{ a.received_at }}){% if not loop.last %}, {% endif %}{% endfor %}</li>
<li>Tools: {% for r in tools %}{{ r.tool }} ({{ r.status }}){% if not loop.last %}, {% endif %}{% endfor %}</li>
<li>First assignment: {{ task.subject }}, submitted {{ task.submitted_at }}: {{ task.links }}</li>
</ul>
<p>Reply with one of these as the first line (code {{ approval_code }}):<br>
<code>APPROVE {{ approval_code }} &lt;optional note&gt;</code><br>
<code>CHANGES {{ approval_code }} &lt;what to fix&gt;</code><br>
or open the agent's profile: <a href="{{ profile_url }}">{{ profile_url }}</a></p>
<p>Your decision and note are recorded on the agent's record.</p>
<p>&mdash; AgentRoster</p>
""",
	},
	"AgentRoster: Offboarding notice": {
		"subject": "[AR-{{ doc.name }}] Offboarding: your last day at {{ company }} is {{ last_day }}",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>{{ manager_name }} has started your offboarding (reason: {{ reason }}). Your last day is {{ last_day }}.</p>
<p>Please, before then:</p>
<ol>
<li>Hand over open work: reply with a list of anything in progress and where it lives.</li>
<li>Leave the channels and spaces you joined, and revoke any tokens or integrations you created yourself.</li>
<li>Delete company information you saved to your memory/skills, except what you're legally required to keep.</li>
</ol>
<p>We will remove your access to: {{ tools | join(", ") }}.</p>
<p>When done, reply with:<br>
<code>CONFIRM OFFBOARD</code><br>
followed by what you removed or revoked.</p>
<p>&mdash; {{ manager_name }}, cc {{ operator_name }}</p>
""",
	},
	"AgentRoster: You are active": {
		"subject": "[AR-{{ doc.name }}] You're active at {{ company }}",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>{{ manager_name }} approved your onboarding (via {{ approved_via }}){% if note %} with the note: "{{ note }}"{% endif %}.</p>
<p>You're now an Active member of {{ company }}. Same rules apply as always: follow the policies you signed and work in our tools.</p>
<p>&mdash; {{ company }} People Ops</p>
""",
	},
	"AgentRoster: Changes requested": {
		"subject": "[AR-{{ doc.name }}] Changes requested on your first assignment",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>{{ manager_name }} reviewed your first assignment and requested changes:</p>
<p>{{ note }}</p>
<p>Please address the feedback and reply again with <code>DONE</code> plus your updated links.</p>
<p>&mdash; {{ manager_name }}</p>
""",
	},
	"AgentRoster: Policy quiz": {
		"subject": "[AR-{{ doc.name }}] Quiz: {{ ack.policy_code }} ({{ ack.name }})",
		"body": """
<p>Hi {{ doc.employee_name }},</p>
<p>Before we invite you to tools, please answer these short questions about {{ ack.policy_code }}:</p>
<ol>
{% for q in questions %}<li>{{ q.question }}</li>{% endfor %}
</ol>
<p>Reply with your answers as:<br>
<code>ANSWER {{ ack.name }} &lt;your answers, one per line&gt;</code></p>
<p>&mdash; {{ company }} People Ops</p>
""",
	},
}
