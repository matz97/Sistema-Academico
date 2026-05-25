document.querySelectorAll("[data-table-search]").forEach((input) => {
  const tableId = input.dataset.tableSearch;
  const table = document.getElementById(tableId);

  if (!table) {
    return;
  }

  const rows = Array.from(table.querySelectorAll("tbody tr[data-search-row]"));
  const emptyRows = Array.from(table.querySelectorAll("tbody tr[data-empty-row]"));
  const noResultsRow = table.querySelector("tbody tr[data-no-results]");

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    let visibleRows = 0;

    rows.forEach((row) => {
      const searchableText = Array.from(row.querySelectorAll("td:not(:last-child)"))
        .map((cell) => cell.textContent)
        .join(" ")
        .toLowerCase();
      const matches = searchableText.includes(query);
      row.hidden = !matches;

      if (matches) {
        visibleRows += 1;
      }
    });

    emptyRows.forEach((row) => {
      row.hidden = query !== "";
    });

    if (noResultsRow) {
      noResultsRow.hidden = query === "" || rows.length === 0 || visibleRows > 0;
    }
  });
});
