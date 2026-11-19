// Search for a landlord by any name it goes by. Reads names.json (built by `landlords build`); nothing leaves the
// browser except, when a search finds no landlord with a page, the words searched (no address or identifier) so we can add names.
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
  // Best matches first. covered: landlords with a page; part: companies in the group of one (they link to its page);
  // small: landlords the regulator's figures show to have fewer than 1,000 homes; unlisted: any other registered
  // landlord, about whose size nothing is said.
  function search(names, text) {
    const q = norm(text);
    if (q.length < 2) return { covered: [], part: [], small: [], unlisted: [] };
    const words = q.split(" ");
    const hits = [];
    for (const e of names) {
      let best = 0;
      for (const k of e.k) best = Math.max(best, score(k, q, words));
      if (best) hits.push([best, e]);
    }
    hits.sort((a, b) => b[0] - a[0] || a[1].n.localeCompare(b[1].n));
    const pick = (keep, n) => hits.filter((h) => keep(h[1])).map((h) => h[1]).slice(0, n);
    return { covered: pick((e) => e.s && !e.g, 8), part: pick((e) => e.s && e.g, 3),
             small: pick((e) => !e.s && e.z, 3), unlisted: pick((e) => !e.s && !e.z, 3) };
  }
  let cache = null;
  function load(root) {
    if (!cache) cache = fetch(root + "names.json").then((r) => r.json());
    return cache;
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  window.WLS = { norm, search, load, esc };

  // The search box on the home page (the script is deferred, so the page is already parsed).
  const form = document.getElementById("search");
  if (form) {
    const root = form.dataset.root || "";
    const input = form.querySelector("input");
    const out = document.getElementById("results");
    const status = document.getElementById("results-status");
    const text = JSON.parse(document.getElementById("search-text").textContent);
    function li(html) { const el = document.createElement("li"); el.innerHTML = html; return el; }
    // Screen readers hear how many were found, half a second after typing stops (or at once on Enter), not the list,
    // which is rebuilt with every letter typed. The same words are not read twice.
    let timer = 0;
    function tell(r, now) {
      clearTimeout(timer);
      // landlords with a page, each counted once, whether found by its own name or a company's in its group
      const n = new Set([...r.covered, ...r.part].map((e) => e.s)).size;
      const words = !WLS.norm(input.value) ? ""
        : n === 1 ? text.found_one : n ? text.found.replace("{count}", n)
        : r.unlisted.length ? text.found_unlisted : r.small.length ? text.found_small : text.found_none;
      timer = setTimeout(() => { if (status.textContent !== words) status.textContent = words; }, now ? 0 : 500);
    }
    async function show(submitted) {
      const names = await load(root);
      const r = search(names, input.value);
      out.innerHTML = "";
      tell(r, submitted);
      if (!WLS.norm(input.value)) return;
      for (const e of r.covered) {
        const also = e.a.length ? ` <span class="hint">(${esc(e.a.slice(0, 3).join(", "))})</span>` : "";
        out.append(li(`<a href="${root}landlords/${e.s}/">${esc(e.n)}</a> <span class="hint">${esc(e.t)}</span>${also}`));
      }
      for (const e of r.part) {
        const link = `<a href="${root}landlords/${e.s}/">${esc(e.g)}</a>`;
        out.append(li(esc(e.r === "group" ? text.group : text.part).replace("{name}", () => esc(e.n)).replace("{group}", () => link)));
      }
      if (!r.covered.length && !r.part.length) {
        for (const e of r.small) out.append(li(esc(text.small.replace("{name}", () => e.n))));
        for (const e of r.unlisted) out.append(li(esc(text.unlisted.replace("{name}", () => e.n))));
        const some = r.small.length || r.unlisted.length;
        out.append(li(esc(some ? text.unlisted_areas : text.none) + ` <a href="${root}areas/">${esc(text.areas)}</a>`));
        if (submitted) {
          // Count the miss, even when it named a landlord we have no page for, so the name can be looked at. Fails
          // quietly where there is no server (the pages opened from disk).
          fetch(root + "api/missed", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ q: input.value.slice(0, 80) }) }).catch(() => {});
        }
      }
    }
    input.addEventListener("input", () => show(false));
    form.addEventListener("submit", (ev) => { ev.preventDefault(); show(true); });
    const q = new URLSearchParams(location.search).get("q");
    if (q) { input.value = q; show(true); }
  }
})();
