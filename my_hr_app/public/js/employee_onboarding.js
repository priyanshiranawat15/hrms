const AGENTROSTER = "my_hr_app.agentroster.agent";

frappe.ui.form.on("Employee Onboarding", {
	refresh(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, "worker_type").then((r) => {
			if (r.message && r.message.worker_type === "Agent") {
				frm.set_intro(
					__("Agent onboarding checklist. Policies must be signed before tool invites can be sent.")
				);
				frm.add_custom_button(__("Send Tool Invites"), () => {
					frappe.call({
						method: `${AGENTROSTER}.send_tool_invites`,
						args: { employee: frm.doc.employee },
						freeze: true,
						freeze_message: __("Sending invite notices..."),
						callback: () => frm.reload_doc(),
					});
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
