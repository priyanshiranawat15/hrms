(function () {
	function add_signup_kind() {
		const $form = $(".form-signup");
		if (!$form.length) {
			const $section = $("section.for-signup");
			if ($section.length && !$("#signup-user-kind").length) {
				$section.find(".page-card-body, .page-card-actions").hide();
				$section.append(
					`<div class="signup-user-kind" style="margin-top:16px">
						<p>There are two users. A human account is created by HR. An AI agent can sign up only with an invite link from HR.</p>
						<label for="agent-invite-link">Invite link</label>
						<input id="agent-invite-link" class="form-control" type="text" autocomplete="off">
						<button class="es-button w-full btn-agent-invite" data-variant="solid" type="button" style="margin-top:12px">Continue</button>
					</div>`
				);
			}
			return;
		}
		if ($("#signup-user-kind").length) {
			return;
		}

		$form.prepend(
			`<div class="form-group signup-user-kind">
				<label for="signup-user-kind">I am</label>
				<select id="signup-user-kind" class="form-control">
					<option value="Human">Human</option>
					<option value="AI Agent">AI Agent</option>
				</select>
			</div>
			<div class="agent-invite-only" style="display:none">
				<p class="text-muted">An AI agent can sign up only with an invite link from HR. Open the link you were sent, or paste it here.</p>
				<div class="form-group">
					<label for="agent-invite-link">Invite link</label>
					<input id="agent-invite-link" class="form-control" type="text" autocomplete="off">
					<div class="field-error"></div>
				</div>
				<div class="form-group">
					<button class="es-button w-full btn-agent-invite" data-variant="solid" type="button">Continue</button>
				</div>
			</div>`
		);

		$("#signup-user-kind").on("change", function () {
			const ai = $(this).val() === "AI Agent";
			$("#signup_fullname, #signup_email").closest(".form-group").toggle(!ai);
			$form.find(".btn-signup").toggle(!ai);
			$form.find(".agent-invite-only").toggle(ai);
		});

	}

	$(document).on("click", ".btn-agent-invite", function () {
		const raw = ($("#agent-invite-link").val() || "").trim();
		let key = raw;
		try {
			const url = new URL(raw, window.location.origin);
			key = url.searchParams.get("key") || raw;
		} catch (e) {
			key = raw;
		}
		if (!key) {
			if (window.login && login.show_field_error) {
				login.show_field_error("agent-invite-link", "Paste the invite link HR sent you.");
			}
			return;
		}
		window.location.href = "/agent-signup?key=" + encodeURIComponent(key);
	});

	document.addEventListener(
		"submit",
		function (event) {
			const form = event.target;
			if (!form || !form.classList || !form.classList.contains("form-signup")) {
				return;
			}
			const kind = document.getElementById("signup-user-kind");
			if (!kind || kind.value !== "AI Agent") {
				return;
			}
			event.preventDefault();
			event.stopPropagation();
			if (window.login && login.show_error_banner) {
				login.show_error_banner("An AI agent can sign up only with an invite link from HR.");
			}
		},
		true
	);

	$(document).on("login_rendered", add_signup_kind);
	$(add_signup_kind);
})();
