import frappe
from frappe.model.document import Document


class AgentTool(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		admin_url: DF.Data | None
		default_role: DF.Data | None
		invite_instructions: DF.Text | None
		machine_user_note: DF.SmallText | None
		removal_instructions: DF.Text | None
		tool_code: DF.Data
		tool_name: DF.Data
	# end: auto-generated types

	def validate(self):
		self.tool_code = (self.tool_code or "").lower().replace(" ", "_")


AGENT_TOOLS = [
	{
		"tool_name": "GitHub",
		"tool_code": "github",
		"invite_instructions": "GitHub org > People > Invite member > enter the agent's email, pick team and role.",
		"removal_instructions": "GitHub org > People > find the machine user > Remove from organization.",
		"admin_url": "https://github.com",
		"default_role": "member",
		"machine_user_note": "GitHub machine user, counts as a paid seat.",
	},
	{
		"tool_name": "Slack",
		"tool_code": "slack",
		"invite_instructions": "Slack workspace admin > Invite people > enter the agent's email, pick channels.",
		"removal_instructions": "Slack workspace admin > Members > deactivate the agent account.",
		"admin_url": "https://slack.com",
		"default_role": "full member",
		"machine_user_note": "",
	},
	{
		"tool_name": "Jira",
		"tool_code": "jira",
		"invite_instructions": "Atlassian admin > Users > Invite user > assign the agent's email and product access.",
		"removal_instructions": "Atlassian admin > Users > deactivate the agent user.",
		"admin_url": "https://www.atlassian.com",
		"default_role": "user",
		"machine_user_note": "",
	},
]
