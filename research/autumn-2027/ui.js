"use strict";
const citySelect = document.querySelector("#city");
if (citySelect) {
  const {matrix,groups} = JSON.parse(document.querySelector("#city-data").textContent);
  const group = document.querySelector("#city-group");
  const rows = Array.from(document.querySelectorAll(".meter"));
  function updateCity() {
    const city = citySelect.value;
    const tracks = groups[group.value];
    const values = tracks.map(([key]) => matrix[key].cities[city]);
    const ceiling = Math.max(1, ...values);
    rows.forEach((row, i) => {
      row.hidden = i >= tracks.length;
      if (row.hidden) return;
      row.dataset.track = tracks[i][0];
      row.querySelector("span").textContent = tracks[i][1];
      row.querySelector("b").textContent = values[i];
      row.querySelector("i").style.setProperty("--w", (values[i] * 100 / ceiling) + "%");
    });
    document.querySelector("#city-count").textContent = city + " · " + group.value + "，条形按本组最高值缩放。";
  }
  citySelect.addEventListener("change", updateCity);
  group.addEventListener("change", updateCity);
  updateCity();
}
const filters = document.querySelector(".filters");
if (filters) {
  const items = Array.from(document.querySelectorAll("[data-item]"));
  const controls = Array.from(filters.querySelectorAll("input,select"));
  function apply() {
    const state = Object.fromEntries(controls.map(el => [el.name,el.value.trim().toLowerCase()]));
    const terms = (state.query || "").split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const item of items) {
      const haystack = item.textContent.toLowerCase();
      const matches = controls.every(el => !state[el.name] || el.name === "query" ||
        (["city","family"].includes(el.name) ? (item.dataset[el.name] || "").toLowerCase().includes(state[el.name]) :
          (item.dataset[el.name] || "").toLowerCase() === state[el.name]));
      item.hidden = !(matches && terms.every(term => haystack.includes(term)));
      if (!item.hidden) visible++;
    }
    document.querySelector("#count").textContent = "显示 " + visible + " / " + items.length + " 条";
    document.querySelector("#empty").hidden = visible !== 0;
  }
  filters.addEventListener("input", apply);
  filters.addEventListener("change", apply);
  filters.addEventListener("reset", () => requestAnimationFrame(apply));
  apply();
}
