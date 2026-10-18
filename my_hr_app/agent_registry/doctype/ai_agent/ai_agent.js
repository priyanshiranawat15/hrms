const EXTRA_FIELDS = [
	"backup_owner",
	"cost_center",
	"job_opening",
	"job_applicant",
	"job_offer",
	"activation_date",
	"profile_section",
	"budget_section",
	"skills_section",
	"api_key",
	"api_key_issued_on",
	"invite_sent_on",
	"invite_expires_on",
];

frappe.ui.form.on("AI Agent", {
	refresh(frm) {
		const has_account = !!frm.doc.system_user;
		const invite_sent = frm.doc.invite_status === "Sent" || frm.doc.invite_status === "Accepted";
		frm.set_df_property("agent_email", "read_only", invite_sent || has_account ? 1 : 0);
		frm.toggle_display("status", !frm.is_new());
		frm.toggle_display("invite_status", !frm.is_new());
		frm.toggle_display("portal_invite_link", !!frm.doc.portal_invite_link);
		frm.toggle_display("system_user", has_account);
		EXTRA_FIELDS.forEach((fieldname) => frm.toggle_display(fieldname, !!frm._show_more));

		if (has_account) {
			frm.set_intro(__("This agent signs in with {0}.", [frm.doc.agent_email]));
		} else {
			frm.set_intro(
				__(
					"Add the bot's name and email. Saving sends one invite link. The agent sets a password from that link, then signs in with that email."
				)
			);
		}

		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("More details"), () => {
			frm._show_more = !frm._show_more;
			EXTRA_FIELDS.forEach((fieldname) => frm.toggle_display(fieldname, !!frm._show_more));
		});

		const blocked = ["Rejected", "Archived", "Deactivated"].includes(frm.doc.status);
		if (!has_account && !blocked) {
			frm.add_custom_button(__("Send portal invite"), () => {
				frappe.call({
					method: "my_hr_app.agent_registry.auth.send_portal_invite",
					args: { agent_name: frm.doc.name },
					freeze: true,
					callback(r) {
						frm.reload_doc();
						if (r.message) {
							frappe.msgprint({
								title: __("Portal invite"),
								indicator: "green",
								message:
									__("The agent opens this link, sets a password, and then signs in:") +
									"<br>" +
									r.message,
							});
						}
					},
				});
			});
		}
	},
	after_save(frm) {
		if (!frm.doc.system_user && frm.doc.invite_status !== "Sent" && frm.doc.invite_status !== "Accepted") {
			frm.reload_doc();
		}
	},
});
