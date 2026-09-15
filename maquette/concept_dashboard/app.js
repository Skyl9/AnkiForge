// Navigation
const navBtns = document.querySelectorAll('.nav-btn[data-view]');
const views = document.querySelectorAll('.view');

navBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        navBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        views.forEach(v => v.classList.add('hidden'));

        const target = 'view-' + btn.getAttribute('data-view');
        const el = document.getElementById(target);
        if(el) {
            el.classList.remove('hidden');
        } else {
            document.getElementById('view-dashboard').classList.remove('hidden');
            alert("Cette vue n'est pas encore implémentée.");
        }
    });
});

// Modals
function openOmnibox() {
    document.getElementById('omnibox-modal').classList.remove('hidden');
    document.querySelector('#omnibox-modal input').focus();
}

function openAutoTagModal() {
    document.getElementById('auto-tag-modal').classList.remove('hidden');
}

function closeModals(event) {
    if (!event || event.target.classList.contains('modal-overlay') || event.currentTarget.classList.contains('btn-primary')) {
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
