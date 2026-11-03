// Search for a landlord by any name it goes by. Reads names.json (built by `landlords build`); nothing leaves the
// browser except, when a search finds nothing, the words searched (no address or identifier) so we can add names.
"use strict";
(function () {
  const DROP = /\b(limited|ltd|plc|cic|the|group|housing association)\b/g;
  // The same as normalise() in src/landlords/register.py.
  function norm(s) {
    return (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/&/g, " and ").replace(/’/g, "'").replace(/\(the\)/g, " ")
      .replace(/[^a-z0-9 ]+/g, " ").replace(DROP, " ").replace(/\s+/g, " ").trim();
  }
  function score(key, q, words) {
    if (key === q) return 100;
    if (key.startsWith(q)) return 80;
    if (key.includes(" " + q)) return 60;
    if (key.includes(q)) return 40;
    const kw = key.split(" ");
    if (words.every((w) => kw.some((k) => k.startsWith(w)))) return 30;
    return 0;
  }
  // Best matches first: covered landlords, then landlords too small to be covered.
  function search(names, text) {
    const q = norm(text);
    if (q.length < 2) return { covered: [], small: [] };
    const words = q.split(" ");
    const hits = [];
    for (const e of names) {
      let best = 0;
      for (const k of e.k) best = Math.max(best, score(k, q, words));
      if (best) hits.push([best, e]);
    }
    hits.sort((a, b) => b[0] - a[0] || a[1].n.localeCompare(b[1].n));
    return { covered: hits.filter((h) => h[1].s).map((h) => h[1]).slice(0, 8),
             small: hits.filter((h) => !h[1].s).map((h) => h[1]).slice(0, 3) };
  }
  let cache = null;
  function load(root) {
    if (!cache) cache = fetch(root + "names.json").then((r) => r.json());
    return cache;
  }
  window.WLS = { norm, search, load };

  // The search box on the home page.
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("search");
    if (!form) return;
    const root = form.dataset.root || "";
    const input = form.querySelector("input");
    const out = document.getElementById("results");
    const text = JSON.parse(document.getElementById("search-text").textContent);
    function li(html) { const el = document.createElement("li"); el.innerHTML = html; return el; }
    function esc(s) { return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }
    async function show(submitted) {
      const names = await load(root);
      const r = search(names, input.value);
      out.innerHTML = "";
      if (!WLS.norm(input.value)) return;
      for (const e of r.covered) {
        const also = e.a.length ? ` <span class="hint">(${esc(e.a.slice(0, 3).join(", "))})</span>` : "";
        out.append(li(`<a href="${root}landlords/${e.s}/index.html">${esc(e.n)}</a> <span class="hint">${esc(e.t)}</span>${also}`));
      }
      if (!r.covered.length) {
        for (const e of r.small) out.append(li(esc(text.small.replace("{name}", e.n))));
        out.append(li(text.none + ` <a href="${root}areas/index.html">${esc(text.areas)}</a>`));
        if (submitted && !r.small.length) {
          // Count the miss. Fails quietly where there is no server (the pages opened from disk).
          fetch(root + "api/missed", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ q: input.value.slice(0, 80) }) }).catch(() => {});
        }
      }
    }
    input.addEventListener("input", () => show(false));
    form.addEventListener("submit", (ev) => { ev.preventDefault(); show(true); });
    const q = new URLSearchParams(location.search).get("q");
    if (q) { input.value = q; show(true); }
  });
})();
