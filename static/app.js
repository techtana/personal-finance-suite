// Personal Finance Suite - Frontend JavaScript

// Format currency for display
function formatCurrency(cents, currencyCode = 'USD') {
    const dollars = cents / 100;
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currencyCode,
    }).format(dollars);
}

// Format date as ISO string (YYYY-MM-DD)
function formatDate(dateObj) {
    if (typeof dateObj === 'string') return dateObj;
    return dateObj.toISOString().split('T')[0];
}

// Parse ISO date string to Date object
function parseDate(isoString) {
    return new Date(isoString + 'T00:00:00Z');
}

// API utility functions
const API = {
    async get(endpoint) {
        const response = await fetch(`/api${endpoint}`);
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },

    async post(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `API error: ${response.status}`);
        }
        return response.json();
    },

    async patch(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `API error: ${response.status}`);
        }
        return response.json();
    },

    async delete(endpoint) {
        const response = await fetch(`/api${endpoint}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.ok;
    },
};

// Modal helper
function showModal(title, content, onConfirm) {
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-lg max-w-md w-full mx-4">
            <div class="p-6">
                <h3 class="text-lg font-semibold text-gray-900">${title}</h3>
                <p class="mt-2 text-gray-600">${content}</p>
                <div class="mt-6 flex space-x-3 justify-end">
                    <button class="px-4 py-2 text-gray-600 hover:text-gray-900 font-medium" onclick="this.closest('.fixed').remove()">Cancel</button>
                    <button class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium" onclick="this.closest('.fixed').remove(); (${onConfirm})()">Confirm</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// Alert helper
function showAlert(message, type = 'info') {
    const colors = {
        success: 'bg-green-100 text-green-800 border-green-200',
        error: 'bg-red-100 text-red-800 border-red-200',
        warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
        info: 'bg-blue-100 text-blue-800 border-blue-200',
    };

    const alert = document.createElement('div');
    alert.className = `fixed top-4 right-4 p-4 rounded border ${colors[type]} z-50`;
    alert.textContent = message;
    document.body.appendChild(alert);

    setTimeout(() => alert.remove(), 5000);
}

// Initialize global Alpine.js data stores
document.addEventListener('alpine:init', () => {
    // Global state can be initialized here if needed
});

// Export for use in templates
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;
window.parseDate = parseDate;
window.API = API;
window.showModal = showModal;
window.showAlert = showAlert;
