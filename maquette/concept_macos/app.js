document.addEventListener("DOMContentLoaded", () => {
  // --- SIDEBAR TOGGLE ---
  const toggleSidebarBtn = document.getElementById("toggle-sidebar");
  const mainSidebar = document.getElementById("main-sidebar");

  if (toggleSidebarBtn && mainSidebar) {
    toggleSidebarBtn.addEventListener("click", () => {
      mainSidebar.classList.toggle("collapsed");
    });
  }

  // --- VIEW NAVIGATION (100% ROBUST) ---
  const allNavTriggers = document.querySelectorAll("[data-view]");
  const allViews = document.querySelectorAll(".view");

  window.navigateToView = function (viewId) {
    if (!viewId) return;

    // 1. Update active state on all triggers
    allNavTriggers.forEach((trigger) => {
      const triggerView = trigger.getAttribute("data-view");
      if (triggerView === viewId || (viewId.startsWith("batch-factory-") && triggerView === "batch-factory")) {
        trigger.classList.add("active");
      } else {
        trigger.classList.remove("active");
      }
    });

    // 2. Hide all views and show the target one robustly
    allViews.forEach((view) => {
      if (view.id === `view-${viewId}`) {
        view.classList.add("active");
        view.classList.remove("hidden");
        // Force inline styles to bypass any CSS specificity issues
        view.style.display = "flex";
        // Reset scroll to top
        view.scrollTop = 0;
      } else {
        view.classList.remove("active");
        view.classList.add("hidden");
        // Force hide
        view.style.display = "none";
      }
    });
  };

  // Attach click listeners safely
  allNavTriggers.forEach((btn) => {
    btn.addEventListener("click", function (e) {
      // Prevent default anchor behavior
      if (this.tagName.toLowerCase() === "a") {
        e.preventDefault();
      }
      let targetViewId = this.getAttribute("data-view");

      if (targetViewId === "batch-factory") {
        const styleSelect = document.getElementById("batch-factory-style-select");
        if (styleSelect) {
            targetViewId = `batch-factory-${styleSelect.value}`;
        } else {
            targetViewId = "batch-factory-cicd"; // fallback
        }
      }

      window.navigateToView(targetViewId);
    });
  });

  // Dynamic update when changing the select in settings
  const styleSelect = document.getElementById("batch-factory-style-select");
  if (styleSelect) {
    styleSelect.addEventListener("change", (e) => {
      // Check if we are currently on a batch factory view
      const isBatchFactoryActive = document.querySelector('.menu-item[data-view="batch-factory"]').classList.contains('active');
      if (isBatchFactoryActive) {
        window.navigateToView(`batch-factory-${e.target.value}`);
      }
    });
  }

  // --- GENERIC TAB SWITCHING ---
  document.querySelectorAll(".tabs, .ide-tabs").forEach((tabGroup) => {
    const tabs = tabGroup.querySelectorAll(".tab, .ide-tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");

        const targetId = tab.getAttribute("data-target");
        if (targetId) {
          const container =
            tabGroup.closest(".inspector-pane") || tabGroup.parentElement;
          const subPanes = container.querySelectorAll(".sub-pane");
          subPanes.forEach((pane) => {
            if (pane.id === targetId) {
              pane.classList.remove("hidden");
              pane.classList.add("active");
            } else {
              pane.classList.add("hidden");
              pane.classList.remove("active");
            }
          });
        }
      });
    });
  });

  // --- COMMAND PALETTE (CMD+K) ---
  const cmdPalette = document.getElementById("cmd-palette");
  const paletteInput = cmdPalette?.querySelector(".palette-input");

  window.toggleCommandPalette = function () {
    if (!cmdPalette) return;
    cmdPalette.classList.toggle("hidden");
    if (!cmdPalette.classList.contains("hidden")) {
      paletteInput.focus();
      paletteInput.value = "";
    }
  };

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      toggleCommandPalette();
    }
    if (
      e.key === "Escape" &&
      cmdPalette &&
      !cmdPalette.classList.contains("hidden")
    ) {
      toggleCommandPalette();
    }
  });

  // --- SETTINGS MODAL ---
  const settingsModal = document.getElementById("settings-modal");

  window.toggleSettingsModal = function () {
    if (settingsModal) settingsModal.classList.toggle("hidden");
  };

  // Close Modals when clicking outside
  window.closeModals = function (e) {
    if (e && e.target.classList.contains("modal-overlay")) {
      e.target.classList.add("hidden");
    } else if (!e) {
      document
        .querySelectorAll(".modal-overlay")
        .forEach((m) => m.classList.add("hidden"));
    }
  };

  // Settings Tabs
  const settingsTabs = document.querySelectorAll(".settings-tab");
  const settingsPanes = document.querySelectorAll(".settings-pane");

  settingsTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      settingsTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      const targetId = tab.getAttribute("data-target");
      settingsPanes.forEach((pane) => {
        if (pane.id === targetId) {
          pane.classList.add("active");
        } else {
          pane.classList.remove("active");
        }
      });
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document
        .querySelectorAll(".modal-overlay:not(.hidden)")
        .forEach((modal) => {
          modal.classList.add("hidden");
        });
    }
  });

  // --- DRAG & DROP FOR IDE TABS ---
  const ideTabLists = document.querySelectorAll(".ide-tabs-list");

  ideTabLists.forEach((list) => {
    let draggedTab = null;

    list.addEventListener("dragstart", (e) => {
      const tab = e.target.closest(".ide-tab");
      if (tab) {
        draggedTab = tab;
        setTimeout(() => {
          tab.style.opacity = "0.5";
        }, 0);
        e.dataTransfer.effectAllowed = "move";
      }
    });

    list.addEventListener("dragend", (e) => {
      const tab = e.target.closest(".ide-tab");
      if (tab) {
        tab.style.opacity = "";
        draggedTab = null;
      }
    });

    list.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      const targetTab = e.target.closest(".ide-tab");
      if (targetTab && targetTab !== draggedTab && list.contains(targetTab)) {
        const rect = targetTab.getBoundingClientRect();
        const next = e.clientX - rect.left > rect.width / 2;
        if (next) {
          list.insertBefore(draggedTab, targetTab.nextSibling);
        } else {
          list.insertBefore(draggedTab, targetTab);
        }
      }
    });
  });

  // --- DETACH PANEL ---
  const detachBtns = document.querySelectorAll(".detach-btn");
  detachBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const panel = e.target.closest(".ide-panel");
      if (panel) {
        const win = window.open("", "_blank", "width=800,height=600");
        if (win) {
          win.document.write(`
                        <html>
                        <head>
                            <title>Panneau Détaché - AnkiForge</title>
                            <style>
                                body {
                                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                                    padding: 40px;
                                    background: #0F1115;
                                    color: #F8FAFC;
                                    display: flex;
                                    flex-direction: column;
                                    align-items: center;
                                    justify-content: center;
                                    height: 100vh;
                                    margin: 0;
                                    text-align: center;
                                }
                                .ph { font-size: 48px; color: #6366F1; margin-bottom: 20px; }
                                h2 { font-weight: 500; margin-bottom: 10px; }
                                p { color: #94A3B8; }
                            </style>
                        </head>
                        <body>
                            <div class="ph ph-squares-out"></div>
                            <h2>Panneau Détaché (Maquette)</h2>
                            <p>Dans la version finale, le panneau serait détaché dans cette nouvelle fenêtre avec tout son contexte.</p>
                        </body>
                        </html>
                    `);
        } else {
          alert(
            "Pop-up bloquée. Le panneau serait détaché dans une nouvelle fenêtre.",
          );
        }
      }
    });
  });
});

// --- IDE-LIKE PREVIEW TOGGLES ---
const toggleBtns = document.querySelectorAll(".view-toggle-btn");
const tableView = document.getElementById("unified-table-view");
const previewView = document.getElementById("unified-preview-view");

toggleBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    // Remove active class from all
    toggleBtns.forEach((b) => {
      b.classList.remove("active");
      b.style.background = "";
      b.style.color = "";
    });

    // Add active class to clicked
    btn.classList.add("active");
    btn.style.background = "var(--bg-hover)";
    btn.style.color = "var(--text-primary)";

    const mode = btn.getAttribute("data-view-mode");

    if (mode === "list") {
      tableView.style.display = "flex";
      previewView.style.display = "none";
    } else if (mode === "preview") {
      tableView.style.display = "none";
      previewView.style.display = "flex";
    } else if (mode === "split") {
      tableView.style.display = "flex";
      previewView.style.display = "flex";
    }
  });
});

// --- TOGGLE VERSO ---
const toggleVersoBtn = document.getElementById("toggle-verso-btn");
const versoContainer = document.getElementById("verso-container");
if (toggleVersoBtn && versoContainer) {
  toggleVersoBtn.addEventListener("click", () => {
    if (versoContainer.style.display === "none") {
      versoContainer.style.display = "flex";
      toggleVersoBtn.innerHTML =
        '<i class="ph ph-eye-slash"></i> <span style="font-size: 11px; margin-left: 4px;">Masquer Verso</span>';
    } else {
      versoContainer.style.display = "none";
      toggleVersoBtn.innerHTML =
        '<i class="ph ph-eye"></i> <span style="font-size: 11px; margin-left: 4px;">Afficher Verso</span>';
    }
  });
}

window.setPreviewDevice = function (device, btn) {
  const frame = document.getElementById("mobile-preview-frame");
  if (!frame) return;

  if (device === "mobile") {
    frame.classList.add("active");
  } else {
    frame.classList.remove("active");
  }

  // Update active button state
  if (btn) {
    const parent = btn.closest(".device-toggles");
    if (parent) {
      parent
        .querySelectorAll(".device-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  const editorVersoToggle = document.getElementById(
    "editor-preview-verso-toggle",
  );
  const editorDivider = document.getElementById("editor-preview-divider");
  const editorVerso = document.getElementById("editor-preview-verso");

  if (editorVersoToggle && editorDivider && editorVerso) {
    editorVersoToggle.addEventListener("change", (e) => {
      if (e.target.checked) {
        editorDivider.style.display = "block";
        editorVerso.style.display = "block";
      } else {
        editorDivider.style.display = "none";
        editorVerso.style.display = "none";
      }
    });
  }
});

window.openHistoryModal = function () {
  const overlay = document.getElementById("history-modal-overlay");
  if (overlay) {
    overlay.style.display = "flex";
  }
};

window.closeHistoryModal = function () {
  const overlay = document.getElementById("history-modal-overlay");
  if (overlay) {
    overlay.style.display = "none";
  }
};
