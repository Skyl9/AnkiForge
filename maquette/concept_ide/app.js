document.addEventListener('DOMContentLoaded', () => {

    // --- VIEW NAVIGATION ---
    const navBtns = document.querySelectorAll('#sidebar .nav-top .nav-btn');
    const views = document.querySelectorAll('.view');
    const inspectorPanes = document.querySelectorAll('.inspector-pane');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state on nav buttons
            navBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const targetViewId = btn.getAttribute('data-view');

            // Show target view
            views.forEach(v => {
                if(v.id === `view-${targetViewId}`) {
                    v.classList.add('active');
                } else {
                    v.classList.remove('active');
                }
            });

            // Show corresponding inspector pane
            inspectorPanes.forEach(pane => {
                if(pane.id === `pane-${targetViewId}`) {
                    pane.classList.add('active');
                } else {
                    pane.classList.remove('active');
                }
            });
            
            // Auto expand inspector if it was collapsed and we change view (optional UX choice)
            const inspector = document.getElementById('inspector');
            if(inspector.classList.contains('collapsed')) {
                inspector.classList.remove('collapsed');
                const toggleIcon = document.querySelector('#toggle-inspector i');
                toggleIcon.classList.remove('fa-chevron-left');
                toggleIcon.classList.add('fa-chevron-right');
            }
        });
    });

    // --- INSPECTOR TOGGLE ---
    const toggleInspectorBtn = document.getElementById('toggle-inspector');
    const inspector = document.getElementById('inspector');
    
    toggleInspectorBtn.addEventListener('click', () => {
        inspector.classList.toggle('collapsed');
        const icon = toggleInspectorBtn.querySelector('i');
        if (inspector.classList.contains('collapsed')) {
            icon.classList.remove('fa-chevron-right');
            icon.classList.add('fa-chevron-left');
        } else {
            icon.classList.remove('fa-chevron-left');
            icon.classList.add('fa-chevron-right');
        }
    });

    // --- GENERIC TAB SWITCHING ---
    document.querySelectorAll('.tabs').forEach(tabGroup => {
        const tabs = tabGroup.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                // Remove active from sibling tabs
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // If tab has data-target, switch sub-panes (used in AI Studio Inspector)
                const targetId = tab.getAttribute('data-target');
                if (targetId) {
                    // Find closest parent container to scope the sub-panes
                    const container = tabGroup.closest('.inspector-pane') || tabGroup.parentElement;
                    const subPanes = container.querySelectorAll('.sub-pane');
                    subPanes.forEach(pane => {
                        if (pane.id === targetId) {
                            pane.classList.remove('hidden');
                            pane.classList.add('active'); // For flex
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
    const paletteInput = cmdPalette.querySelector('.palette-input');

    window.toggleCommandPalette = function() {
        cmdPalette.classList.toggle('hidden');
        if (!cmdPalette.classList.contains('hidden')) {
            paletteInput.focus();
            paletteInput.value = '';
        }
    };

    // Keyboard shortcut (Cmd+K or Ctrl+K)
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleCommandPalette();
        }
        // Close on Escape
        if (e.key === 'Escape' && !cmdPalette.classList.contains('hidden')) {
            toggleCommandPalette();
        }
    });

    // Close when clicking outside palette container
    cmdPalette.addEventListener('click', (e) => {
        if (e.target === cmdPalette) {
            toggleCommandPalette();
        }
    });

    // --- SETTINGS MODAL ---
    const settingsModal = document.getElementById('settings-modal');
    
    window.toggleSettingsModal = function() {
        settingsModal.classList.toggle('hidden');
    };

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

    // Close Settings on Escape or clicking outside
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            toggleSettingsModal();
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !settingsModal.classList.contains('hidden')) {
            toggleSettingsModal();
        }
    });
});
