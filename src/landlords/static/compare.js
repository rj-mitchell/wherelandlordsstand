// Compare up to three landlords side by side, from the per-landlord JSON files `landlords build` writes. The choice is
// kept in the address (?l=slug,slug) so a comparison can be shared. Everything is drawn from published figures and
// our bands; each landlord's bands are against its own group of similar landlords.
"use strict";
document.addEventListener("DOMContentLoaded", async () => {
  const box = document.getElementById("compare");
  if (!box) return;
  const root = box.dataset.root;
  const text = JSON.parse(document.getElementById("compare-text").textContent);
  const input = document.getElementById("add");
  const picks = document.getElementById("picks");
  const table = document.getElementById("table");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  let chosen = (new URLSearchParams(location.search).get("l") || "").split(",").filter(Boolean).slice(0, 3);
  const data = {};

  async function get(slug) {
    if (!data[slug]) data[slug] = await fetch(`${root}data/landlords/${slug}.json`).then((r) => r.ok ? r.json() : null);
    return data[slug];
  }
  function save() {
    const url = new URL(location.href);
    if (chosen.length) url.searchParams.set("l", chosen.join(",")); else url.searchParams.delete("l");
    history.replaceState(null, "", url);
  }
  const band = (b) => b ? text.bands[b - 1] : text.none;
  const pct = (v) => v == null ? "–" : `${v.toFixed(1)}%`;

  async function draw() {
    const rows = (await Promise.all(chosen.map(get))).filter(Boolean);
    picks.innerHTML = rows.map((l) => `<li>${esc(l.name)} <button type="button" data-s="${esc(l.slug)}" aria-label="${esc(text.remove)} ${esc(l.name)}">${esc(text.remove)}</button></li>`).join("");
    if (!rows.length) { table.innerHTML = `<p>${esc(text.empty)}</p>`; return; }
    const line = (label, f) => `<tr><th scope="row">${esc(label)}</th>${rows.map((l) => `<td>${f(l)}</td>`).join("")}</tr>`;
    let html = `<div class="scroll"><table class="cmp"><thead><tr><th scope="col"></th>${rows.map((l) => `<th scope="col"><a href="${root}landlords/${esc(l.slug)}/index.html">${esc(l.name)}</a></th>`).join("")}</tr></thead><tbody>`;
    html += line(text.type, (l) => esc(l.type));
    html += line(text.homes, (l) => l.homes ? esc(l.homes.toLocaleString("en-GB")) : "–");
    html += line(text.grade, (l) => l.grade ? `${esc(l.grade)} <span class="hint">(${esc(l.grade_date)})</span>` : esc(text.not_graded));
    html += line(text.overall, (l) => `${pct(l.overall)}<br><span class="hint">${esc(band(l.overall_band))}</span>`);
    for (const [i, p] of rows[0].pillars.entries()) html += line(p.label, (l) => esc(band(l.pillars[i] && l.pillars[i].band)));
    html += line(text.peer, (l) => esc(l.peer_group || "–"));
    html += line(text.ombudsman, (l) => l.ombudsman ? `${esc(l.ombudsman.at_fault)} ${esc(text.at_fault)}<br><span class="hint">${esc(l.ombudsman.findings)} ${esc(text.findings)}, ${esc(l.ombudsman.period)}</span>` : esc(text.no_report));
    html += line(text.safety, (l) => esc(l.safety == null ? "–" : l.safety ? text.all_done : text.not_all_done));
    html += `</tbody></table></div><p class="hint">${esc(text.caveat)}</p>`;
    table.innerHTML = html;
  }

  picks.addEventListener("click", (ev) => {
    const s = ev.target.dataset && ev.target.dataset.s;
    if (s) { chosen = chosen.filter((x) => x !== s); save(); draw(); }
  });
  const list = document.getElementById("suggest");
  input.addEventListener("input", async () => {
    const names = await WLS.load(root);
    const r = WLS.search(names, input.value).covered.slice(0, 6);
    list.innerHTML = r.map((e) => `<li><button type="button" data-s="${esc(e.s)}">${esc(e.n)}</button></li>`).join("");
  });
  list.addEventListener("click", (ev) => {
    const s = ev.target.dataset && ev.target.dataset.s;
    if (s && !chosen.includes(s) && chosen.length < 3) { chosen.push(s); save(); draw(); }
    input.value = ""; list.innerHTML = "";
  });
  draw();
});
