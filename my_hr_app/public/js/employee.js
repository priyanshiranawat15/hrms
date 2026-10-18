const AGENT_HIDDEN_FIELDS = [
	"gender",
	"date_of_birth",
	"salutation",
	"middle_name",
	"last_name",
	"marital_status",
	"blood_group",
	"family_background",
	"health_details",
	"personal_email",
	"prefered_contact_email",
	"create_user_automatically",
	"create_user_permission",
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
];

const AGENT_HIDDEN_SECTIONS = [
	"personal_details",
	"contact_details",
	"attendance_and_leave_details",
	"salary_information",
	"profile_tab",
	"employment_details",
	"exit",
	"connections_tab",
	"bank_details_section",
	"passport_details_section",
	"emergency_contact_details",
	"address_section",
];

const AGENT_SKIPPED_ASSIGNMENTS = ["Leave Policy", "Salary Structure", "Shift", "Shift Schedule"];

function show_field(frm, fieldname, show) {
	if (!frm.fields_dict[fieldname] && !frm.meta.fields.some((field) => field.fieldname === fieldname)) {
		return;
	}
	frm.set_df_property(fieldname, "hidden", show ? 0 : 1);
	frm.toggle_display(fieldname, show);
}

const AGENTROSTER = "my_hr_app.agentroster.agent";

function show_status_progress(frm) {
	const statuses = [
		"Draft",
		"Policies Sent",
		"Policies Acknowledged",
		"Tool Access",
		"Ready for Assignment",
		"First Assignment",
		"Awaiting Approval",
		"Active",
	];
	if (frm.doc.worker_type !== "Agent" || !frm.doc.agent_status) {
		frm.dashboard.hide_progress();
		return;
	}
	if (["Offboarding", "Offboarded"].includes(frm.doc.agent_status)) {
		frm.dashboard.set_headline(__("Agent is {0}.", [frm.doc.agent_status]));
		return;
	}
	let steps = [];
	statuses.forEach((status) => {
		steps.push({
			title: status,
			depends_on: null,
			value: 1,
			condition_met: statuses.indexOf(frm.doc.agent_status) >= statuses.indexOf(status),
		});
	});
	frm.dashboard.add_progress(__("Agent Status"), steps);
}

frappe.ui.form.on("Employee", {
	refresh(frm) {
		const agent = frm.doc.worker_type === "Agent";
		show_field(frm, "agent_profile", agent);
		show_field(frm, "operator", agent);
		AGENT_HIDDEN_FIELDS.forEach((fieldname) => show_field(frm, fieldname, !agent));
		AGENT_HIDDEN_SECTIONS.forEach((fieldname) => show_field(frm, fieldname, !agent));
		if (frm.layout) {
			frm.layout.refresh_sections();
		}
		if (!agent) {
			return;
		}
		frm.dashboard.set_headline(
			__("AI agent. Personal, pay, leave, and attendance details stay empty.")
		);
		show_status_progress(frm);

		frm.add_custom_button(__("Add Agent"), () => {
			frappe.new_doc("Employee", { worker_type: "Agent" });
		});
		// agent lifecycle actions
		if (frm.doc.agent_status === "Draft") {
			frm.add_custom_button(__("Start Onboarding"), () => {
				frappe.call({
					method: `${AGENTROSTER}.start_onboarding`,
					args: { employee: frm.doc.name },
					freeze: true,
					freeze_message: __("Starting onboarding..."),
					callback: () => frm.reload_doc(),
				});
			});
		}
		if (frm.doc.agent_status === "Ready for Assignment") {
			frm.add_custom_button(__("Send First Assignment"), () => {
				let d = new frappe.ui.Dialog({
					title: __("First Assignment"),
					fields: [
						{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1 },
						{
							fieldname: "description",
							fieldtype: "Small Text",
							label: __("What to do"),
							reqd: 1,
						},
						{
							fieldname: "acceptance",
							fieldtype: "Small Text",
							label: __("Done means"),
						},
					],
					primary_action_label: __("Send"),
					primary_action(values) {
						frappe.call({
							method: `${AGENTROSTER}.start_first_assignment`,
							args: { employee: frm.doc.name, ...values },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
						d.hide();
					},
				});
				d.show();
			});
		}
		if (frm.doc.agent_status === "Awaiting Approval") {
			frm.add_custom_button(__("Approve to Active"), () => {
				let d = new frappe.ui.Dialog({
					title: __("Approve {0} to Active", [frm.doc.employee_name]),
					fields: [{ fieldname: "note", fieldtype: "Small Text", label: __("Decision note") }],
					primary_action_label: __("Approve"),
					primary_action(values) {
						frappe.call({
							method: `${AGENTROSTER}.approve_agent`,
							args: { employee: frm.doc.name, note: values.note },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
						d.hide();
					},
				});
				d.show();
			});
			frm.add_custom_button(__("Request Changes"), () => {
				let d = new frappe.ui.Dialog({
					title: __("Request Changes"),
					fields: [
						{ fieldname: "note", fieldtype: "Small Text", label: __("What to fix"), reqd: 1 },
					],
					primary_action_label: __("Send"),
					primary_action(values) {
						frappe.call({
							method: `${AGENTROSTER}.request_changes`,
							args: { employee: frm.doc.name, note: values.note },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
						d.hide();
					},
				});
				d.show();
			});
		}
		if (frm.doc.agent_status !== "Offboarding" && frm.doc.agent_status !== "Offboarded") {
			frm.add_custom_button(__("Offboard"), () => {
				let d = new frappe.ui.Dialog({
					title: __("Offboard {0}", [frm.doc.employee_name]),
					fields: [
						{ fieldname: "reason", fieldtype: "Data", label: __("Reason"), reqd: 1 },
						{ fieldname: "last_day", fieldtype: "Date", label: __("Last day") },
					],
					primary_action_label: __("Start Offboarding"),
					primary_action(values) {
						frappe.call({
							method: `${AGENTROSTER}.start_offboarding`,
							args: {
								employee: frm.doc.name,
								reason: values.reason,
								last_day: values.last_day,
							},
							freeze: true,
							callback: () => frm.reload_doc(),
						});
						d.hide();
					},
				});
				d.show();
			});
		}
		setTimeout(() => {
			AGENT_SKIPPED_ASSIGNMENTS.forEach((label) => {
				frm.remove_custom_button(__(label), __("Create Assignments"));
			});
		}, 600);
	},
	worker_type(frm) {
		frm.trigger("refresh");
	},
});
