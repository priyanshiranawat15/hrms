frappe.listview_settings["AI Agent"] = {
	add_fields: ["status", "risk_tier", "execution_mode"],
	filters: [["status", "!=", "Archived"]],
	get_indicator(doc) {
		const colors = {
			Requested: "orange",
			"Under Review": "blue",
			Approved: "cyan",
			Onboarding: "yellow",
			Active: "green",
			Deactivated: "red",
			Archived: "gray",
			Rejected: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
