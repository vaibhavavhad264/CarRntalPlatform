document.addEventListener("DOMContentLoaded", () => {
  const $ = id => document.getElementById(id);
  const money = n => "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });

  // Mobile menu
  if ($("burger")) $("burger").onclick = () => $("navbar").classList.toggle("open");

  // Account dropdown
  const acct = $("acct");
  if (acct) {
    $("ddBtn").onclick = e => { e.stopPropagation(); acct.classList.toggle("open"); };
    document.addEventListener("click", e => { if (!acct.contains(e.target)) acct.classList.remove("open"); });
  }

  // Light / dark mode (remembered in the browser)
  const root = document.documentElement, tb = $("themeBtn");
  const paint = () => { if (tb) tb.textContent = root.getAttribute("data-theme") === "dark" ? "☀️" : "🌙"; };
  paint();
  if (tb) tb.onclick = () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    paint();
  };

  // Flash messages fade out
  document.querySelectorAll(".flash").forEach(f => setTimeout(() => (f.style.opacity = 0), 4500));

  // Favourite hearts
  document.querySelectorAll(".favorite").forEach(b => b.onclick = () => {
    b.classList.toggle("on"); b.textContent = b.classList.contains("on") ? "♥" : "♡";
  });

  // Scroll reveal
  const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && e.target.classList.add("in")), { threshold: .15 });
  document.querySelectorAll(".reveal").forEach(el => io.observe(el));

  // FAQ accordion (one open at a time)
  document.querySelectorAll(".faq-q").forEach(btn => btn.onclick = () => {
    const item = btn.parentElement, open = item.classList.contains("open");
    document.querySelectorAll(".faq").forEach(i => { i.classList.remove("open"); i.querySelector(".faq-a").style.maxHeight = 0; });
    if (!open) { item.classList.add("open"); const a = item.querySelector(".faq-a"); a.style.maxHeight = a.scrollHeight + "px"; }
  });

  // Admin tabs
  document.querySelectorAll(".tab-btn").forEach(btn => btn.onclick = () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("on"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("on"));
    btn.classList.add("on"); $(btn.dataset.tab).classList.add("on");
  });

  // Registration validation (Python validates again on the server)
  const reg = $("registerForm");
  if (reg) reg.onsubmit = e => {
    const f = reg.elements, errs = [];
    if (!f.username.value.trim()) errs.push("Username is required.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.value)) errs.push("Enter a valid email.");
    if (f.password.value.length < 6) errs.push("Password needs at least 6 characters.");
    if (f.password.value !== f.confirm.value) errs.push("Passwords do not match.");
    const age = Number(f.age.value);
    if (!Number.isInteger(age) || age < 18) errs.push("Age must be a whole number, 18 or above.");
    if (!f.license.value) errs.push("Answer yes or no for the driving license.");
    $("errs").innerHTML = errs.join("<br>");
    if (errs.length) e.preventDefault();
  };

  // Sorting applies instantly
  if ($("sortSel")) $("sortSel").onchange = () => $("filterForm").submit();

  // Booking: validation + live estimate (the server recalculates the real amounts)
  const bf = $("bookingForm");
  if (bf) {
    const price = Number(bf.dataset.price), first = bf.dataset.first === "1", msg = $("estimate");
    const get = () => {
      const f = bf.elements;
      if (!f.start_date.value || !f.start_time.value || !f.end_date.value || !f.end_time.value) return null;
      return [new Date(f.start_date.value + "T" + f.start_time.value), new Date(f.end_date.value + "T" + f.end_time.value)];
    };
    const set = (id, v) => { if ($(id)) $(id).textContent = v; };
    const update = () => {
      ["sumHours", "sumSub", "sumDisc", "sumTotal"].forEach(i => set(i, "—")); msg.textContent = "";
      const d = get(); if (!d) return;
      if (d[0] < new Date()) return (msg.textContent = "Start cannot be in the past.");
      if (d[1] <= d[0]) return (msg.textContent = "End must be after the start.");
      const hrs = Math.ceil((d[1] - d[0]) / 3600000), sub = hrs * price, disc = first ? Math.round(sub * 30) / 100 : 0;
      set("sumHours", hrs + " hour" + (hrs > 1 ? "s" : "")); set("sumSub", money(sub));
      set("sumDisc", "− " + money(disc)); set("sumTotal", money(sub - disc));
    };
    bf.addEventListener("input", update);
    bf.onsubmit = e => {
      const d = get();
      if (!d || d[0] < new Date() || d[1] <= d[0]) { e.preventDefault(); msg.textContent = "Please enter valid future dates, with end after start."; }
    };
  }

  // Confirmation dialogs (confirm booking / cancel booking)
  document.querySelectorAll("form[data-confirm]").forEach(f =>
    f.onsubmit = e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
});
