// @ts-check
function openCopyModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Kopiera dag</h2>
      <p class="note">Kopierar från en dag till en annan inom området <b>${escapeHtml(state.areas.find(a => a.id === state.areaId)?.name || "Alla")}</b>.</p>
      <label>Från år</label><input id="cp-fy" type="number" value="${state.year}" />
      <label>Från vecka</label><input id="cp-fw" type="number" value="${state.week}" />
      <label>Från dag</label>
      <select id="cp-fd">${[1,2,3,4,5,6,7].map((d) => `<option value="${d}" ${d === state.weekday ? "selected" : ""}>${DAYS[d]}</option>`).join("")}</select>
      <label>Till år</label><input id="cp-ty" type="number" value="${state.year}" />
      <label>Till vecka</label><input id="cp-tw" type="number" value="${state.week}" />
      <label>Till dag</label>
      <select id="cp-td">${[1,2,3,4,5,6,7].map((d) => `<option value="${d}">${DAYS[d]}</option>`).join("")}</select>
      <label class="modal-checkbox"><input id="cp-ow" type="checkbox" /> Skriv över befintliga celler i målet</label>
      <div class="actions">
        <button id="cp-cancel">Avbryt</button>
        <button id="cp-go" class="primary">Kopiera</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  document.getElementById("cp-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("cp-go").addEventListener("click", async () => {
    const field = (id) => /** @type {HTMLInputElement} */ (document.getElementById(id));
    const copyPayload = {
      from_year: Number(field("cp-fy").value),
      from_week: Number(field("cp-fw").value),
      from_weekday: Number(field("cp-fd").value),
      to_year: Number(field("cp-ty").value),
      to_week: Number(field("cp-tw").value),
      to_weekday: Number(field("cp-td").value),
      area_id: state.areaId,
      overwrite: field("cp-ow").checked,
    };
    try {
      const r = await api.post("/api/schedule/copy", copyPayload);
      invalidateScheduleAllCache();
      showToast(`Kopierade ${r.copied} celler`);
      backdrop.remove();
      if (targetMatchesCurrentDay(copyPayload.to_year, copyPayload.to_week, copyPayload.to_weekday)) {
        const undoSnapshots = snapshotHoursFromCells(r.applied || []);
        pushScheduleUndo("kopiera dag", undoSnapshots);
        applySegmentsByHourResponse(r.applied);
        scheduleSummaryRefresh(0, { refreshCalculator: true });
      }
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });
}
