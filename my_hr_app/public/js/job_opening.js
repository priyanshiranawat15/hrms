frappe.ui.form.on("Job Opening", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		if (frm.doc.worker_kind === "AI Agent") {
			frm.add_custom_button(__("AI Agent"), () => open_agent_from_opening(frm), __("Create"));
		}
	},
});

function open_agent_from_opening(frm) {
	frappe.db.get_value("AI Agent", { job_opening: frm.doc.name }, "name").then((r) => {
		if (r.message && r.message.name) {
			frappe.set_route("Form", "AI Agent", r.message.name);
			return;
		}
		frappe.new_doc("AI Agent", {
			agent_name: frm.doc.job_title,
			company: frm.doc.company,
			department: frm.doc.department,
			designation: frm.doc.designation,
			job_opening: frm.doc.name,
		});
	});
}
