// static/js/landing.js
// Scroll effects for the landing page only (loaded from dashboard/landing.html):
//   - reading progress bar and a header shadow once the page scrolls
//   - header link for the section being read gets underlined (scroll spy)
//   - hero layers drift at different speeds (parallax); the preview card tilts toward the cursor
//   - "How it works" timeline draws itself and lights up each step
//   - final call-to-action zooms in as it arrives; feature cards get a cursor spotlight
// Visitors who prefer reduced motion get the final state with no movement.

(function () {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    const progressBar = document.querySelector("[data-scroll-progress]");
    const nav = document.querySelector("[data-site-nav]");
    const hero = document.querySelector("[data-hero]");
    const parallaxEls = Array.from(document.querySelectorAll("[data-parallax]"));
    const timeline = document.querySelector("[data-timeline]");
    const timelineFill = document.querySelector("[data-timeline-fill]");
    const dots = Array.from(document.querySelectorAll("[data-step]"));
    const stepCards = Array.from(document.querySelectorAll("[data-step-card]"));
    const zoomEls = Array.from(document.querySelectorAll("[data-zoom-in]"));

    const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

    // Light up the first `count` steps (0-3)
    function setActiveSteps(count) {
        dots.forEach((dot) => dot.classList.toggle("is-active", Number(dot.dataset.step) < count));
        stepCards.forEach((card) => card.classList.toggle("is-active", Number(card.dataset.stepCard) < count));
    }

    function update() {
        const vh = window.innerHeight;
        const scrollY = window.scrollY;
        const maxScroll = document.documentElement.scrollHeight - vh;

        if (progressBar) {
            progressBar.style.transform = `scaleX(${maxScroll > 0 ? clamp(scrollY / maxScroll) : 0})`;
        }
        if (nav) {
            nav.classList.toggle("shadow-soft", scrollY > 8);
        }
        if (reduceMotion) return;

        // Parallax only while the hero is still on screen
        if (hero && scrollY < hero.offsetTop + hero.offsetHeight) {
            parallaxEls.forEach((el) => {
                el.style.transform = `translate3d(0, ${(scrollY * parseFloat(el.dataset.parallax)).toFixed(1)}px, 0)`;
            });
        }

        // The timeline fills while it travels from 85% to 35% of the screen height.
        // On phones it's hidden, so each step card lights up as it scrolls into view.
        if (timeline && timeline.offsetParent !== null) {
            const progress = clamp((vh * 0.85 - timeline.getBoundingClientRect().top) / (vh * 0.5));
            timelineFill.style.transform = `scaleX(${progress})`;
            setActiveSteps(progress <= 0.02 ? 0 : progress < 0.5 ? 1 : progress < 0.98 ? 2 : 3);
        } else {
            stepCards.forEach((card) => card.classList.toggle("is-active", card.getBoundingClientRect().top < vh * 0.75));
        }

        // Call to action grows from 92% to full size as it comes in
        zoomEls.forEach((el) => {
            const progress = clamp((vh - el.getBoundingClientRect().top) / (vh * 0.6));
            el.style.transform = `scale(${(0.92 + 0.08 * progress).toFixed(4)})`;
            el.style.opacity = (0.4 + 0.6 * progress).toFixed(3);
        });
    }

    // Run at most once per animation frame while scrolling
    let ticking = false;
    function requestUpdate() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            update();
            ticking = false;
        });
    }
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);

    if (reduceMotion) {
        if (timelineFill) timelineFill.style.transform = "scaleX(1)";
        setActiveSteps(3);
    }
    update();

    // ---------- Scroll spy: underline the header link for the section in view ----------
    const navLinks = Array.from(document.querySelectorAll("[data-nav-link]"));
    if (navLinks.length && "IntersectionObserver" in window) {
        const setActiveLink = (id) => navLinks.forEach((link) => link.classList.toggle("is-active", link.dataset.navLink === id));
        const spy = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    setActiveLink(entry.target === hero ? null : entry.target.id);
                });
            },
            // A thin band across the middle of the screen decides which section is "current"
            { rootMargin: "-45% 0px -50% 0px" }
        );
        navLinks.forEach((link) => {
            const section = document.getElementById(link.dataset.navLink);
            if (section) spy.observe(section);
        });
        if (hero) spy.observe(hero);
    }

    if (reduceMotion || !finePointer) return;

    // ---------- Hero preview card tilts toward the cursor ----------
    const tiltCard = document.querySelector("[data-tilt]");
    if (tiltCard) {
        const area = tiltCard.parentElement;
        area.addEventListener("mousemove", (e) => {
            const rect = tiltCard.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            tiltCard.style.transform = `rotateX(${(-y * 6).toFixed(2)}deg) rotateY(${(x * 8).toFixed(2)}deg)`;
        });
        area.addEventListener("mouseleave", () => {
            tiltCard.style.transform = "";
        });
    }

    // ---------- Feature cards: glow follows the cursor (CSS reads --mx/--my) ----------
    document.querySelectorAll(".feature-card").forEach((card) => {
        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            card.style.setProperty("--mx", `${e.clientX - rect.left}px`);
            card.style.setProperty("--my", `${e.clientY - rect.top}px`);
        });
    });
})();
