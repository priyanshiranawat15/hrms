frappe.ui.form.on("Agent Action Check", {
	refresh(frm) {
		if (frm.doc.decision === "Refused") {
			frm.set_intro(__("Refused by the signed policy. This cannot be permitted."), "red");
		} else if (frm.doc.decision === "Needs permission" && frm.doc.status === "Waiting for permission") {
			frm.set_intro(__("The agent asked. Nothing goes out until you grant permission."), "orange");
			frm.add_custom_button(__("Grant permission"), () => {
				frappe.call({
					method: "my_hr_app.agentroster.controls.grant_permission",
					args: { name: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		} else if (frm.doc.status === "Permitted") {
			frm.set_intro(__("You permitted this one request. The next one asks again."), "green");
		} else if (frm.doc.decision === "Allowed") {
			frm.set_intro(__("Allowed by the signed policy. It stays a draft inside the portal."), "green");
		}
	},
});
