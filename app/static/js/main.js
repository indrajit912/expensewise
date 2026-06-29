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

    // Add loading spinners on email-sending form submissions
    const forms = document.querySelectorAll('form');
    forms.forEach((form) => {
        form.addEventListener('submit', (e) => {
            const action = form.getAttribute('action') || '';
            const path = window.location.pathname;
            
            const isEmailForm = 
                path.includes('/support') ||
                path.includes('/register') ||
                path.includes('/reset_password_request') ||
                action.includes('/resend-otp') ||
                action.includes('/verify-otp') ||
                path.includes('/reset_password');
                
            if (isEmailForm) {
                if (form.checkValidity && !form.checkValidity()) {
                    return;
                }
                
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    setTimeout(() => {
                        submitBtn.disabled = true;
                        if (submitBtn.tagName === 'INPUT') {
                            submitBtn.value = 'Sending...';
                        } else {
                            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Sending...';
                        }
                    }, 0);
                }
            }
        });
    });
});
