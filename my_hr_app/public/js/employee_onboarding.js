const AGENTROSTER = "my_hr_app.agentroster.agent";

frappe.ui.form.on("Employee Onboarding", {
	refresh(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, "worker_type").then((r) => {
			if (r.message && r.message.worker_type === "Agent") {
				frm.set_intro(
					__("Agent onboarding checklist. Policies must be signed before tool invites go out. The agent's manager sends the GitHub and Slack invites.")
				);
				frm.add_custom_button(__("Mark Tool Invites Sent"), () => {
					agentroster_mark_invites_sent(frm.doc.employee, frm.doc.employee_name, () => frm.reload_doc());
				});
				frm.add_custom_button(__("Mark Tool Joined"), () => {
					agentroster_mark_tool_joined(frm.doc.employee, () => frm.reload_doc());
				});
				frm.add_custom_button(__("Verify Tool Row"), () => {
					const rows = (frm.doc.activities || []).filter(
						(row) => row.access_status === "Accepted" && row.activity_kind === "Tool Invite"
					);
					if (!rows.length) {
						frappe.msgprint(__("No Accepted tool rows to verify yet."));
						return;
					}
					let d = new frappe.ui.Dialog({
						title: __("Verify Tool Row"),
						fields: [
							{
								fieldname: "row",
								fieldtype: "Select",
								label: __("Tool Row"),
								options: rows.map((r) => r.agent_tool).join("\n"),
								reqd: 1,
							},
						],
						primary_action_label: __("Mark Verified"),
						primary_action(values) {
							const match = rows.find((r) => r.agent_tool === values.row);
							frappe.call({
								method: `${AGENTROSTER}.verify_tool_row`,
								args: { employee: frm.doc.employee, row_name: match.name },
								freeze: true,
								callback: () => frm.reload_doc(),
							});
							d.hide();
						},
					});
					d.show();
				});
			}
		});
	},
});

function agentroster_mark_invites_sent(employee, employee_name, done) {
	frappe.confirm(
		__(
			"Have you sent the tool invites (GitHub from you, Slack from Slack on your behalf)? {0} gets an email for each one.",
			[employee_name || __("The agent")]
		),
		() => {
			frappe.call({
				method: `${AGENTROSTER}.send_tool_invites`,
				args: { employee },
				freeze: true,
				freeze_message: __("Sending invite notices..."),
				callback: done,
			});
		}
	);
}

function agentroster_mark_tool_joined(employee, done) {
	frappe.call({
		method: `${AGENTROSTER}.get_tool_rows`,
		args: { employee },
		callback(r) {
			const rows = (r.message || []).filter((row) => row.access_status === "Invited");
			if (!rows.length) {
				frappe.msgprint(__("No tool invites are waiting. Mark the invites sent first."));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Mark Tool Joined"),
				fields: [
					{
						fieldname: "tool",
						fieldtype: "Select",
						label: __("Tool"),
						options: rows.map((row) => row.agent_tool).join("\n"),
						default: rows[0].agent_tool,
						reqd: 1,
					},
					{
						fieldname: "evidence",
						fieldtype: "Data",
						label: __("Agent's username, handle, or link"),
						reqd: 1,
					},
				],
				primary_action_label: __("Mark Joined"),
				primary_action(values) {
					const match = rows.find((row) => row.agent_tool === values.tool);
					frappe.call({
						method: `${AGENTROSTER}.mark_tool_joined`,
						args: { employee, row_name: match.name, evidence: values.evidence },
						freeze: true,
						callback: done,
					});
					d.hide();
				},
			});
			d.show();
		},
	});
}
