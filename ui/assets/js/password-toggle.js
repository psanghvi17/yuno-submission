(function () {
    function initPasswordToggle(root) {
        var scope = root || document;
        scope.querySelectorAll("[data-password-toggle]").forEach(function (group) {
            var input = group.querySelector('input[type="password"]');
            var btn = group.querySelector("[data-password-toggle-btn]");
            if (!input || !btn || btn.dataset.passwordToggleBound === "1") {
                return;
            }
            btn.dataset.passwordToggleBound = "1";

            var iconHidden = group.querySelector("[data-password-icon-hidden]");
            var iconVisible = group.querySelector("[data-password-icon-visible]");

            btn.addEventListener("click", function () {
                var show = input.type === "password";
                input.type = show ? "text" : "password";
                if (iconHidden) {
                    iconHidden.classList.toggle("d-none", show);
                }
                if (iconVisible) {
                    iconVisible.classList.toggle("d-none", !show);
                }
                btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initPasswordToggle();
        });
    } else {
        initPasswordToggle();
    }

    window.initPasswordToggle = initPasswordToggle;
})();
