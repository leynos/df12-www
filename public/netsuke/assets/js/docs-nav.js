(function () {
    "use strict";

    function init() {
        var selects = document.querySelectorAll("[data-docs-nav-select]");
        selects.forEach(function (select) {
            select.addEventListener("change", function () {
                if (select.value && select.value !== window.location.pathname) {
                    window.location.assign(select.value);
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
