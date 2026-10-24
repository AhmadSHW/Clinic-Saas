// static/js/dashboard.js
// Staff dashboard only: stat numbers count up on load, and the banner clock stays current.

(function () {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // The rest of the site shows Western digits in Arabic too, so ask Intl for them
    const pageLang = document.documentElement.lang || "en";
    const lang = pageLang.startsWith("ar") ? "ar-u-nu-latn" : pageLang;

    // ---------- Count-up for stat tile values ----------
    if (!reduceMotion) {
        const numberFormat = new Intl.NumberFormat(lang);
        document.querySelectorAll("[data-count-up]").forEach((el) => {
            const target = parseInt(el.textContent.replace(/[^\d]/g, ""), 10);
            if (!target) return;
            const duration = 900;
            const start = performance.now();
            const easeOut = (t) => 1 - Math.pow(1 - t, 3);
            function frame(now) {
                const t = Math.min(1, (now - start) / duration);
                el.textContent = numberFormat.format(Math.round(target * easeOut(t)));
                if (t < 1) requestAnimationFrame(frame);
            }
            el.textContent = numberFormat.format(0);
            requestAnimationFrame(frame);
        });
    }

    // ---------- Live clock in the welcome banner ----------
    const clock = document.querySelector("[data-live-clock]");
    if (clock) {
        // Clinic time zone (from Django), not the visitor's computer
        const timeZone = clock.dataset.timezone || undefined;
        const dateFormat = new Intl.DateTimeFormat(lang, { weekday: "long", day: "numeric", month: "long", timeZone });
        const timeFormat = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit", hour12: false, timeZone });
        const tick = () => {
            const now = new Date();
            clock.textContent = `${dateFormat.format(now)} · ${timeFormat.format(now)}`;
        };
        tick();
        // Line up with the start of the next minute, then update every minute
        setTimeout(() => {
            tick();
            setInterval(tick, 60000);
        }, (60 - new Date().getSeconds()) * 1000);
    }
})();
