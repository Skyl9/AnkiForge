const navItems = document.querySelectorAll('.glass-nav-item[data-view]');
const views = document.querySelectorAll('.view');

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        navItems.forEach(n => n.classList.remove('active'));
        item.classList.add('active');

        views.forEach(v => v.classList.add('hidden'));

        const target = 'view-' + item.getAttribute('data-view');
        const el = document.getElementById(target);
        if(el) {
            el.classList.remove('hidden');
        }
    });
});

function openOmnibox() {
    document.getElementById('omnibox-modal').classList.remove('hidden');
    document.querySelector('#omnibox-modal input').focus();
}

function openAutoTagModal() {
    alert("Maquette Auto-Tag Glassmorphism à venir.");
}

function closeModals(event) {
    if (!event || event.target.classList.contains('modal-overlay')) {
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));
    }
}

document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        openOmnibox();
    }
    if (e.key === 'Escape') closeModals();
});
