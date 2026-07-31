/* Scroll-spy for the docs sidebar.
 *
 * Docs pages list their in-page sub-headings in the desktop sidebar as
 * `a.sidebar-link--sub` anchors. As the reader scrolls, mark the link
 * whose section contains the current reading position with the same
 * `active` class the stylesheet already uses (red left border). Pages
 * without sub-links are left alone.
 */
(function () {
    "use strict";

    var OFFSET = 96; // sticky navbar (4rem) plus breathing room

    function init() {
        var links = Array.prototype.slice.call(
            document.querySelectorAll('#sidebar a.sidebar-link--sub[href^="#"]')
        );
        var targets = links
            .map(function (link) {
                var el = document.getElementById(
                    decodeURIComponent(link.getAttribute("href").slice(1))
                );
                return el ? { link: link, el: el } : null;
            })
            .filter(Boolean);
        if (!targets.length) {
            return;
        }

        var current = null;

        function setActive(entry) {
            if (entry === current) {
                return;
            }
            if (current) {
                current.link.classList.remove("active");
                current.link.removeAttribute("aria-current");
            }
            if (entry) {
                entry.link.classList.add("active");
                entry.link.setAttribute("aria-current", "location");
            }
            current = entry;
        }

        function update() {
            var atBottom =
                window.innerHeight + window.scrollY >=
                document.documentElement.scrollHeight - 2;
            if (atBottom) {
                setActive(targets[targets.length - 1]);
                return;
            }
            var active = null;
            for (var i = 0; i < targets.length; i += 1) {
                if (targets[i].el.getBoundingClientRect().top <= OFFSET) {
                    active = targets[i];
                }
            }
            setActive(active);
        }

        var ticking = false;
        function onScroll() {
            if (!ticking) {
                ticking = true;
                window.requestAnimationFrame(function () {
                    ticking = false;
                    update();
                });
            }
        }

        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll, { passive: true });
        update();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
