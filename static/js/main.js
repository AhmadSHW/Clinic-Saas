// static/js/main.js

document.addEventListener("DOMContentLoaded", function () {
    // Auto-dismiss alert messages after 4 seconds
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = "opacity 0.5s ease";
            alert.style.opacity = "0";
            setTimeout(function () {
                alert.remove();
            }, 500);
        }, 4000);
    });
});
// Scroll-reveal animation for elements with the "reveal-on-scroll" class
document.addEventListener("DOMContentLoaded", function () {
    const revealEls = document.querySelectorAll(".reveal-on-scroll");

    if (revealEls.length && "IntersectionObserver" in window) {
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
});
