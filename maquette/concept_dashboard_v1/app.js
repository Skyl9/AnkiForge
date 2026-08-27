// Navigation Sidebar
const menuItems = document.querySelectorAll('.menu-item[data-view]');
const views = document.querySelectorAll('.view');

menuItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();

        // Remove active class from all menu items
        menuItems.forEach(m => m.classList.remove('active'));
        // Add active class to clicked item
        item.classList.add('active');

        // Hide all views
        views.forEach(v => v.classList.add('hidden'));

        // Show target view
        const targetViewId = 'view-' + item.getAttribute('data-view');
        const targetView = document.getElementById(targetViewId);
        if (targetView) {
            targetView.classList.remove('hidden');
        } else {
            // Fallback for not-yet-implemented views
            views.forEach(v => v.classList.add('hidden'));
            document.getElementById('view-dashboard').classList.remove('hidden');
            alert("Vue en cours de maquettage !");
        }
    });
});

// Right Panel Toggle (Editor)
function switchRightPanel(panelId) {
    // Buttons
    const buttons = document.querySelectorAll('.toggle-btn');
    buttons.forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    // Content
    const contents = document.querySelectorAll('.right-content');
    contents.forEach(c => c.classList.add('hidden'));
    document.getElementById('right-' + panelId).classList.remove('hidden');
}

// Modals
function openOmnibox() {
    document.getElementById('omnibox-modal').classList.remove('hidden');
    document.querySelector('#omnibox-modal input').focus();
}

function openAutoTagModal() {
    document.getElementById('auto-tag-modal').classList.remove('hidden');
}

function closeModals(event) {
    if (!event || event.target.classList.contains('modal-overlay') || event.currentTarget.classList.contains('btn-icon') || event.currentTarget.tagName === 'BUTTON') {
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        openOmnibox();
    }
    if (e.key === 'Escape') {
        closeModals();
    }
});
