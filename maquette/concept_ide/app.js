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

  // --- DETACH PANEL SIMULATION ---
  const detachBtns = document.querySelectorAll(".detach-btn");
  detachBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const panel = e.target.closest(".ide-panel");
      if (!panel) return;
      
      const activeTab = panel.querySelector(".ide-tab.active");
      if (!activeTab) return;
      
      const targetId = activeTab.getAttribute("data-target");
      const content = panel.querySelector(`#${targetId}`);
      if (!content) return;
      
      const title = activeTab.textContent ? activeTab.textContent.trim() : activeTab.innerText.trim();
      const iconClass = activeTab.querySelector("i") ? activeTab.querySelector("i").className : "ph ph-cube-transparent";

      // Hide active tab and content
      activeTab.style.display = "none";
      content.style.display = "none";
      
      // Create empty state placeholder
      const emptyState = document.createElement("div");
      emptyState.className = "empty-state-dock";
      emptyState.innerHTML = `
          <i class="ph ph-squares-down"></i>
          <h3>Panneau Libre</h3>
          <p>Glissez-déposez l'onglet ou la fenêtre ici pour l'ancrer.</p>
          <div style="display: flex; gap: 12px; margin-top: 16px;">
              <button class="mock-add-btn" style="background-color: var(--accent-primary); color: white; border: none; border-radius: var(--radius-sm); padding: 8px 16px; font-size: 12px; font-weight: 600; cursor: pointer; transition: background 0.2s;">Ouvrir un onglet...</button>
              <button class="mock-restore-btn" style="background-color: var(--bg-hover); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 8px 16px; font-size: 12px; font-weight: 500; cursor: pointer; transition: background 0.2s;">Restaurer tout</button>
          </div>
      `;
      panel.appendChild(emptyState);
      
      // Create mock floating window
      const floatWin = document.createElement("div");
      floatWin.className = "mock-floating-window";
      floatWin.style.left = `${panel.getBoundingClientRect().left + 40}px`;
      floatWin.style.top = `${panel.getBoundingClientRect().top + 40}px`;
      
      floatWin.innerHTML = `
          <div class="mock-floating-header">
              <span class="mock-floating-title"><i class="${iconClass}"></i> ${title} (Détaché)</span>
              <button class="btn-icon small close-float-btn" title="Ancrer à nouveau"><i class="ph ph-x"></i></button>
          </div>
          <div class="mock-floating-content">
              <div class="ide-tabs-list">
                  <div class="ide-tab active" draggable="true" style="cursor: grab;">
                      <i class="${iconClass}"></i>
                      ${title}
                  </div>
              </div>
              <div style="margin-top: 12px; height: calc(100% - 48px); overflow: auto;">
                  <div class="sub-pane active flex-col h-full">
                      <p style="color: var(--text-secondary); font-size: 13px;">Contenu du panneau détaché en cours de manipulation.</p>
                  </div>
              </div>
          </div>
      `;
      document.body.appendChild(floatWin);
      
      // Handle moving the floating window
      const header = floatWin.querySelector(".mock-floating-header");
      let isDragging = false;
      let startX, startY;
      
      header.addEventListener("mousedown", (e) => {
          if (e.target.closest(".close-float-btn")) return;
          isDragging = true;
          startX = e.clientX - floatWin.offsetLeft;
          startY = e.clientY - floatWin.offsetTop;
          floatWin.style.borderColor = "var(--accent-primary)";
      });
      
      document.addEventListener("mousemove", (e) => {
          if (!isDragging) return;
          floatWin.style.left = `${e.clientX - startX}px`;
          floatWin.style.top = `${e.clientY - startY}px`;
      });
      
      document.addEventListener("mouseup", () => {
          isDragging = false;
          floatWin.style.borderColor = "";
      });
      
      // Drag events to restore/dock back
      const floatTab = floatWin.querySelector(".ide-tab");
      
      floatTab.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", targetId);
          e.dataTransfer.effectAllowed = "move";
      });
      
      // Drag over empty target
      emptyState.addEventListener("dragover", (e) => {
          e.preventDefault();
          emptyState.classList.add("drag-over");
      });
      
      emptyState.addEventListener("dragleave", () => {
          emptyState.classList.remove("drag-over");
      });
      
      emptyState.addEventListener("drop", (e) => {
          e.preventDefault();
          emptyState.classList.remove("drag-over");
          
          // Restore tab & content
          activeTab.style.display = "";
          content.style.display = "";
          emptyState.remove();
          floatWin.remove();
      });
      
      // Close button docks back
      floatWin.querySelector(".close-float-btn").addEventListener("click", () => {
          activeTab.style.display = "";
          content.style.display = "";
          emptyState.remove();
          floatWin.remove();
      });

      // Mock actions dock back
      emptyState.querySelector(".mock-add-btn").addEventListener("click", () => {
          activeTab.style.display = "";
          content.style.display = "";
          emptyState.remove();
          floatWin.remove();
      });

      emptyState.querySelector(".mock-restore-btn").addEventListener("click", () => {
          activeTab.style.display = "";
          content.style.display = "";
          emptyState.remove();
          floatWin.remove();
      });
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

// --- CUSTOM CONTEXT MENU SIMULATION ---
document.addEventListener("DOMContentLoaded", () => {
  const contextMenu = document.getElementById("custom-context-menu");
  if (!contextMenu) return;

  let rightClickedTab = null;

  document.body.addEventListener("contextmenu", (e) => {
    const tab = e.target.closest(".ide-tab");
    if (!tab) {
      contextMenu.style.display = "none";
      return;
    }

    e.preventDefault();
    rightClickedTab = tab;

    // Check if the tab is inside a floating window
    const isFloating = !!tab.closest(".mock-floating-window");
    const detachAction = contextMenu.querySelector(".detach-tab-action");
    const dockAction = contextMenu.querySelector(".dock-tab-action");

    if (isFloating) {
      detachAction.style.display = "none";
      dockAction.style.display = "flex";
    } else {
      detachAction.style.display = "flex";
      dockAction.style.display = "none";
    }

    // Position menu at cursor
    contextMenu.style.left = `${e.pageX}px`;
    contextMenu.style.top = `${e.pageY}px`;
    contextMenu.style.display = "flex";
  });

  // Hide context menu when clicking outside
  document.addEventListener("click", () => {
    contextMenu.style.display = "none";
  });

  // Handle menu actions
  contextMenu.querySelector(".close-tab-action").addEventListener("click", () => {
    if (rightClickedTab) {
      // Simulate close
      rightClickedTab.style.display = "none";
      const targetId = rightClickedTab.getAttribute("data-target");
      if (targetId) {
        const content = document.getElementById(targetId);
        if (content) content.style.display = "none";
      }
    }
  });

  contextMenu.querySelector(".detach-tab-action").addEventListener("click", () => {
    if (rightClickedTab) {
      // Find parent panel
      const panel = rightClickedTab.closest(".ide-panel");
      if (panel) {
        // Trigger the detach button click
        const detachBtn = panel.querySelector(".detach-panel-btn");
        if (detachBtn) detachBtn.click();
      }
    }
  });

  contextMenu.querySelector(".dock-tab-action").addEventListener("click", () => {
    if (rightClickedTab) {
      // Find the close button of the mock floating window to dock it back
      const floatWin = rightClickedTab.closest(".mock-floating-window");
      if (floatWin) {
        const closeBtn = floatWin.querySelector(".close-float-btn");
        if (closeBtn) closeBtn.click();
      }
    }
  });
});
