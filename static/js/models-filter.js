(function () {
  const searchInput = document.getElementById("modelSearch");
  const projectFilter = document.getElementById("projectFilter");
  const grid = document.getElementById("modelsGrid");
  const resultCount = document.getElementById("modelResultCount");
  const noResults = document.getElementById("modelsNoResults");

  if (!searchInput || !projectFilter || !grid || !resultCount) return;

  const cards = Array.from(grid.querySelectorAll(".searchable-card"));
  const total = cards.length;

  function normalize(value) {
    return String(value || "").trim().toLocaleLowerCase("th-TH");
  }

  function updateResults() {
    const query = normalize(searchInput.value);
    const selectedProject = projectFilter.value;
    let visibleCount = 0;

    cards.forEach((card) => {
      const searchableText = normalize(card.dataset.searchText);
      const projectName = card.dataset.project || "";
      const matchesQuery = !query || searchableText.includes(query);
      const matchesProject = !selectedProject || projectName === selectedProject;
      const shouldShow = matchesQuery && matchesProject;

      card.hidden = !shouldShow;
      if (shouldShow) visibleCount += 1;
    });

    resultCount.textContent = `แสดง ${visibleCount} จาก ${total} โมเดล`;
    if (noResults) noResults.hidden = visibleCount !== 0;
  }

  searchInput.addEventListener("input", updateResults);
  projectFilter.addEventListener("change", updateResults);
  updateResults();
})();
