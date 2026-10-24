// static/js/main.js
// Small, dependency-free behaviours shared by every page.

document.addEventListener("DOMContentLoaded", function () {
    setUpSidebar();
    setUpToasts();
    setUpForms();
    setUpRevealOnScroll();
});

// ---------- Off-canvas sidebar (phones/tablets) ----------
function setUpSidebar() {
    const body = document.body;
    const backdrop = document.querySelector("[data-sidebar-backdrop]");

    function open() {
        body.classList.add("sidebar-open", "overflow-hidden");
        if (backdrop) backdrop.classList.remove("hidden");
    }
    function close() {
        body.classList.remove("sidebar-open", "overflow-hidden");
        if (backdrop) backdrop.classList.add("hidden");
    }

    document.querySelectorAll("[data-sidebar-open]").forEach((el) => el.addEventListener("click", open));
    document.querySelectorAll("[data-sidebar-close]").forEach((el) => el.addEventListener("click", close));
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") close();
    });
}

// ---------- Toasts ----------
function dismissToast(toast) {
    toast.style.transition = "opacity .3s ease, transform .3s ease";
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-6px)";
    setTimeout(() => toast.remove(), 300);
}

function setUpToasts() {
    document.querySelectorAll("[data-toast]").forEach((toast, index) => {
        toast.querySelector("[data-toast-close]")?.addEventListener("click", () => dismissToast(toast));
        // Errors stay longer so there's time to read them
        const delay = (toast.classList.contains("toast-error") ? 8000 : 5000) + index * 400;
        let timer = setTimeout(() => dismissToast(toast), delay);
        toast.addEventListener("mouseenter", () => clearTimeout(timer));
        toast.addEventListener("mouseleave", () => {
            timer = setTimeout(() => dismissToast(toast), 2500);
        });
    });
}

// ---------- Confirm dialog + loading buttons ----------
// <form data-confirm="Cancel this appointment?"> asks first.
// Every form disables its submit button and shows a spinner while submitting,
// unless it has data-no-loading.
function setUpForms() {
    const modal = document.getElementById("confirm-modal");
    let pendingForm = null;

    function openModal(form) {
        pendingForm = form;
        modal.querySelector("[data-confirm-text]").textContent = form.dataset.confirm;
        const ok = modal.querySelector("[data-confirm-ok]");
        if (form.dataset.confirmButton) ok.textContent = form.dataset.confirmButton;
        modal.classList.remove("hidden");
        modal.classList.add("flex");
        ok.focus();
    }
    function closeModal() {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
        pendingForm = null;
    }

    if (modal) {
        const okButton = modal.querySelector("[data-confirm-ok]");
        const okDefault = okButton.textContent;
        modal.querySelectorAll("[data-confirm-cancel]").forEach((el) => el.addEventListener("click", closeModal));
        okButton.addEventListener("click", () => {
            const form = pendingForm;
            closeModal();
            okButton.textContent = okDefault;
            if (form) {
                form.dataset.confirmed = "1";
                form.requestSubmit ? form.requestSubmit() : form.submit();
            }
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
        });
    }

    document.addEventListener("submit", (e) => {
        const form = e.target;
        if (form.dataset.confirm && modal && !form.dataset.confirmed) {
            e.preventDefault();
            openModal(form);
            return;
        }
        if (form.hasAttribute("data-no-loading")) return;

        const button = e.submitter || form.querySelector('[type="submit"]');
        if (button && !button.disabled) {
            // Disable on the next tick so the click still submits the form
            setTimeout(() => {
                button.disabled = true;
                button.insertAdjacentHTML("afterbegin", '<span class="spinner" aria-hidden="true"></span>');
            }, 0);
        }
    });

    // Back/forward cache can restore a page with a disabled button
    window.addEventListener("pageshow", () => {
        document.querySelectorAll("button[disabled] .spinner").forEach((spinner) => {
            spinner.parentElement.disabled = false;
            spinner.remove();
        });
        document.querySelectorAll("form[data-confirmed]").forEach((form) => delete form.dataset.confirmed);
    });
}

// ---------- Landing page: reveal sections as they scroll into view ----------
function setUpRevealOnScroll() {
    const revealEls = document.querySelectorAll(".reveal-on-scroll");
    if (!revealEls.length) return;

    if (!("IntersectionObserver" in window)) {
        revealEls.forEach((el) => el.classList.add("revealed"));
        return;
    }
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("revealed");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.15 }
    );
    revealEls.forEach((el) => observer.observe(el));
}
