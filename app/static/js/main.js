// ExpenseWise JavaScript Actions

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss alert boxes after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-danger)');
    alerts.forEach((alert) => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Handle interactive validation or delete prompts
    const deleteButtons = document.querySelectorAll('.confirm-delete');
    deleteButtons.forEach((btn) => {
        btn.addEventListener('click', (e) => {
            if (!confirm('Are you sure you want to delete this item? This action is irreversible.')) {
                e.preventDefault();
            }
        });
    });
});
