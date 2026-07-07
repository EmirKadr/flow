// @ts-check
async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      // Fallback nedan hanterar webbläsare som visar sidan utan clipboard-rättighet.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Urklipp kunde inte användas.");
}

function bindResultActions(root) {
  initializeAllocationResultMaps(root);
  root.querySelector("[data-edit-carrier-clusters]")?.addEventListener("click", () => {
    allocationTrack("settings_modal_open", {
      control_id: "allocation-edit-carrier-clusters",
      control_label: "Transportörskluster",
      detail: { modal: "carrier_clusters" },
    });
    openAllocationCarrierClusterModal();
  });
  root.querySelectorAll("[data-follow-up-flow]").forEach((button) => {
    button.addEventListener("click", async () => {
      allocationTrack("follow_up_flow_start", {
        flow_id: button.dataset.followUpFlow || "",
        control_id: "allocation-follow-up-flow",
        control_label: button.textContent || "Foljdflode",
        detail: { follow_up_flow: button.dataset.followUpFlow || "" },
      });
      await runAllocationFlow(flowById(button.dataset.followUpFlow));
    });
  });
  root.querySelectorAll("[data-copy-text-result]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const text = button.closest(".allocation-text-result-wrap")?.querySelector("[data-result-text]")?.textContent || "";
        await writeClipboardText(text);
        allocationTrack("copy_text", {
          control_id: "allocation-copy-text-result",
          control_label: button.getAttribute("aria-label") || "Kopiera text",
          detail: {
            copied_length: text.length,
            copied_line_count: text ? text.split(/\r?\n/).filter((line) => line.trim()).length : 0,
          },
        });
        showToast("Text kopierad", "success", 2000);
      } catch (error) {
        allocationTrack("copy_text_error", {
          control_id: "allocation-copy-text-result",
          control_label: button.getAttribute("aria-label") || "Kopiera text",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte kopiera texten.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-copy-column]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.copyKey;
      const columnIndex = button.dataset.copyColumn;
      const columnMeta = allocationTableEventMeta(key, columnIndex);
      try {
        const sessionId = allocationState.result?.data?.session_id;
        if (!sessionId || !key || columnIndex == null) {
          allocationTrack("copy_column_blocked", {
            ...columnMeta,
            control_id: "allocation-copy-column",
            control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
            status: "blocked",
            detail: { reason: "missing_result" },
          });
          throw new Error("Resultatet kunde inte hittas.");
        }
        const data = await allocationJson(
          `${ALLOCATION_API}/table-column/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}/${encodeURIComponent(columnIndex)}`,
        );
        await writeClipboardText(data.text || "");
        allocationTrack("copy_column", {
          ...columnMeta,
          control_id: "allocation-copy-column",
          control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
          detail: {
            copy_mode: "manual",
            copied_line_count: String(data.text || "").split(/\r?\n/).filter((line) => line.trim()).length,
          },
        });
        showToast("Kolumn kopierad", "success", 2000);
      } catch (error) {
        allocationTrack("copy_column_error", {
          ...columnMeta,
          control_id: "allocation-copy-column",
          control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte kopiera kolumnen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-excel]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.openExcel;
      const tableMeta = allocationTableEventMeta(key);
      try {
        await allocationJson(`${ALLOCATION_API}/open-excel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: allocationState.result.data.session_id, key }),
        });
        allocationTrack("open_excel", {
          ...tableMeta,
          control_id: "allocation-open-excel",
          control_label: button.textContent || "Oppna i Excel",
        });
        showToast("Excel öppnas", "success", 2500);
      } catch (error) {
        allocationTrack("open_excel_error", {
          ...tableMeta,
          control_id: "allocation-open-excel",
          control_label: button.textContent || "Oppna i Excel",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message, "error");
      }
    });
  });
  root.querySelectorAll("[data-download-csv]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.downloadCsv;
      const tableMeta = allocationTableEventMeta(key);
      try {
        const sessionId = allocationState.result?.data?.session_id;
        if (!sessionId || !key) {
          allocationTrack("download_blocked", {
            ...tableMeta,
            control_id: "allocation-download-csv",
            control_label: button.textContent || "Ladda ner CSV",
            status: "blocked",
            detail: { reason: "missing_result" },
          });
          throw new Error("Resultatet kunde inte hittas.");
        }
        const filename = `${button.dataset.downloadLabel || key}.csv`;
        await api.download(`${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`, filename);
        allocationTrack("export", {
          ...tableMeta,
          control_id: "allocation-download-csv",
          control_label: button.textContent || "Ladda ner CSV",
          detail: { format: "csv" },
        });
      } catch (error) {
        allocationTrack("download_error", {
          ...tableMeta,
          control_id: "allocation-download-csv",
          control_label: button.textContent || "Ladda ner CSV",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte ladda ner CSV-filen.", "error");
      }
    });
  });
}
