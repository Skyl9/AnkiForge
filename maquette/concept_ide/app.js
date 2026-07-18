document.addEventListener('DOMContentLoaded', () => {

    // --- SIDEBAR TOGGLE ---
    const toggleSidebarBtn = document.getElementById('toggle-sidebar');
    const mainSidebar = document.getElementById('main-sidebar');

    if (toggleSidebarBtn && mainSidebar) {
        toggleSidebarBtn.addEventListener('click', () => {
            mainSidebar.classList.toggle('collapsed');
        });
    }

    // --- VIEW NAVIGATION (100% ROBUST) ---
    const allNavTriggers = document.querySelectorAll('[data-view]');
    const allViews = document.querySelectorAll('.view');

    window.navigateToView = function(viewId) {
        if (!viewId) return;

        // 1. Update active state on all triggers
        allNavTriggers.forEach(trigger => {
            if (trigger.getAttribute('data-view') === viewId) {
                trigger.classList.add('active');
            } else {
                trigger.classList.remove('active');
            }
        });

        // 2. Hide all views and show the target one robustly
        allViews.forEach(view => {
            if (view.id === `view-${viewId}`) {
                view.classList.add('active');
                view.classList.remove('hidden');
                // Force inline styles to bypass any CSS specificity issues
                view.style.display = 'flex';
                // Reset scroll to top
                view.scrollTop = 0;
            } else {
                view.classList.remove('active');
                view.classList.add('hidden');
                // Force hide
                view.style.display = 'none';
            }
        });
    };

    // Attach click listeners safely
    allNavTriggers.forEach(btn => {
        btn.addEventListener('click', function(e) {
            // Prevent default anchor behavior
            if (this.tagName.toLowerCase() === 'a') {
                e.preventDefault();
            }
            const targetViewId = this.getAttribute('data-view');
            window.navigateToView(targetViewId);
        });
    });



    // --- GENERIC TAB SWITCHING ---
    document.querySelectorAll('.tabs').forEach(tabGroup => {
        const tabs = tabGroup.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const targetId = tab.getAttribute('data-target');
                if (targetId) {
                    const container = tabGroup.closest('.inspector-pane') || tabGroup.parentElement;
                    const subPanes = container.querySelectorAll('.sub-pane');
                    subPanes.forEach(pane => {
                        if (pane.id === targetId) {
                            pane.classList.remove('hidden');
                            pane.classList.add('active');
                        } else {
                            pane.classList.add('hidden');
                            pane.classList.remove('active');
                        }
                    });
                }
            });
        });
    });

    // --- COMMAND PALETTE (CMD+K) ---
    const cmdPalette = document.getElementById('cmd-palette');
    const paletteInput = cmdPalette?.querySelector('.palette-input');

    window.toggleCommandPalette = function() {
        if(!cmdPalette) return;
        cmdPalette.classList.toggle('hidden');
        if (!cmdPalette.classList.contains('hidden')) {
            paletteInput.focus();
            paletteInput.value = '';
        }
    };

    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleCommandPalette();
        }
        if (e.key === 'Escape' && cmdPalette && !cmdPalette.classList.contains('hidden')) {
            toggleCommandPalette();
        }
    });

    // --- SETTINGS MODAL ---
    const settingsModal = document.getElementById('settings-modal');
    
    window.toggleSettingsModal = function() {
        if(settingsModal) settingsModal.classList.toggle('hidden');
    };

    // Close Modals when clicking outside
    window.closeModals = function(e) {
        if(e && e.target.classList.contains('modal-overlay')) {
            e.target.classList.add('hidden');
        } else if(!e) {
            document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));
        }
    }

    // Settings Tabs
    const settingsTabs = document.querySelectorAll('.settings-tab');
    const settingsPanes = document.querySelectorAll('.settings-pane');

    settingsTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            settingsTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            const targetId = tab.getAttribute('data-target');
            settingsPanes.forEach(pane => {
                if (pane.id === targetId) {
                    pane.classList.add('active');
                } else {
                    pane.classList.remove('active');
                }
            });
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(modal => {
                modal.classList.add('hidden');
            });
        }
    });
});
