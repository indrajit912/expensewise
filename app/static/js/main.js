// ExpenseWise JavaScript Actions

function formatIndianNumber(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) {
        return "";
    }
    const val = parseFloat(amount);
    const isNegative = val < 0;
    const absVal = Math.abs(val);
    
    const parts = absVal.toFixed(2).split('.');
    let intPart = parts[0];
    const decPart = parts[1] || '00';
    
    let result = '';
    if (intPart.length <= 3) {
        result = intPart;
    } else {
        const lastThree = intPart.substring(intPart.length - 3);
        let remaining = intPart.substring(0, intPart.length - 3);
        const groups = [];
        while (remaining.length > 0) {
            if (remaining.length >= 2) {
                groups.unshift(remaining.substring(remaining.length - 2));
                remaining = remaining.substring(0, remaining.length - 2);
            } else {
                groups.unshift(remaining);
                remaining = "";
            }
        }
        groups.push(lastThree);
        result = groups.join(',');
    }
    
    let formatted = result + '.' + decPart;
    if (isNegative) {
        formatted = '-' + formatted;
    }
    return formatted;
}

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
