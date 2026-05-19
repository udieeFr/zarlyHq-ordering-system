/**
 * Admin AJAX Utility Module
 * Handles smooth form submissions, inline updates, and toast notifications
 */

const AdminAJAX = {
  /**
   * Show a toast notification
   * @param {string} message - The message to display
   * @param {string} type - 'success', 'error', 'warning', 'info'
   * @param {number} duration - Auto-dismiss after ms (0 = no auto-dismiss)
   */
  showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('adminToastStack') || (() => {
      const div = document.createElement('div');
      div.id = 'adminToastStack';
      div.style.cssText = 'display:flex;flex-direction:column;gap:0.5rem;position:fixed;top:80px;right:20px;z-index:9999;max-width:400px;';
      document.body.appendChild(div);
      return div;
    })();

    const toast = document.createElement('div');
    toast.className = `admin-toast admin-toast--${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');

    const bgColor = type === 'error' ? '#fef2f2' :
                    type === 'warning' ? '#fffbeb' :
                    type === 'success' ? '#f0fdf4' : '#eff6ff';
    const borderColor = type === 'error' ? '#fca5a5' :
                        type === 'warning' ? '#fcd34d' :
                        type === 'success' ? '#86efac' : '#93c5fd';
    const textColor = type === 'error' ? '#991b1b' :
                      type === 'warning' ? '#92400e' :
                      type === 'success' ? '#166534' : '#1e40af';

    const iconPath = type === 'error' ?
      '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>' :
      type === 'warning' ?
      '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>' :
      type === 'success' ?
      '<polyline points="20 6 9 17 4 12"/>' :
      '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>';

    toast.innerHTML = `
      <div style="display:flex;align-items:flex-start;gap:0.75rem;padding:0.875rem 1.1rem;border-radius:0.875rem;font-size:0.85rem;line-height:1.45;background:${bgColor};border:1px solid ${borderColor};color:${textColor};animation:toastIn .2s ease;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:1px;">
          ${iconPath}
        </svg>
        <span style="flex:1;">${message}</span>
        <button onclick="this.closest('.admin-toast').remove()" style="background:none;border:none;cursor:pointer;padding:0;opacity:0.55;line-height:1;flex-shrink:0;margin-top:1px;color:inherit;" aria-label="Dismiss">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    `;

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        toast.style.transition = 'opacity .4s, transform .4s';
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-4px)';
        setTimeout(() => toast.remove(), 420);
      }, duration);
    }

    return toast;
  },

  /**
   * Submit a form via AJAX
   * @param {HTMLFormElement} form - The form to submit
   * @param {Object} options - Configuration options
   */
  async submitForm(form, options = {}) {
    const {
      onSuccess = null,
      onError = null,
      showToast = true,
      updateRow = null,
      resetForm = false,
      preventDefault = true
    } = options;

    if (preventDefault) {
      form.addEventListener('submit', e => e.preventDefault(), { once: true });
    }

    const button = form.querySelector('button[type="submit"]');
    const originalText = button ? button.textContent : '';
    const originalHTML = button ? button.innerHTML : '';

    try {
      // Show loading state
      if (button) {
        button.disabled = true;
        button.innerHTML = '<span style="display:inline-flex;align-items:center;gap:0.4rem;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:spin .8s linear infinite;"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10" stroke-dasharray="15.7" stroke-dashoffset="0"/></svg> Processing...</span>';
      }

      const formData = new FormData(form);
      const response = await fetch(form.action || form.getAttribute('data-action'), {
        method: form.method || 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      const data = await response.json();

      if (response.ok) {
        if (showToast) {
          this.showToast(data.message || 'Success!', 'success');
        }

        if (updateRow && data.html) {
          const row = document.getElementById(updateRow);
          if (row) {
            row.outerHTML = data.html;
          }
        }

        if (resetForm) {
          form.reset();
        }

        if (onSuccess) {
          onSuccess(data);
        }
      } else {
        throw new Error(data.message || 'Request failed');
      }
    } catch (error) {
      if (showToast) {
        this.showToast(error.message || 'An error occurred', 'error');
      }
      if (onError) {
        onError(error);
      }
    } finally {
      // Restore button state
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
        if (originalHTML) {
          button.innerHTML = originalHTML;
        }
      }
    }
  },

  /**
   * Make a simple AJAX request
   * @param {string} url - The URL to request
   * @param {Object} options - Configuration options
   */
  async request(url, options = {}) {
    const {
      method = 'POST',
      data = null,
      showToast = true,
      onSuccess = null,
      onError = null,
      updateElement = null
    } = options;

    const button = options.button;
    if (button) {
      button.disabled = true;
      button.setAttribute('data-loading', 'true');
    }

    try {
      const headers = {
        'X-Requested-With': 'XMLHttpRequest'
      };

      const fetchOptions = {
        method,
        headers
      };

      if (data) {
        if (data instanceof FormData) {
          fetchOptions.body = data;
        } else {
          headers['Content-Type'] = 'application/json';
          fetchOptions.body = JSON.stringify(data);
        }
      }

      const response = await fetch(url, fetchOptions);
      const result = await response.json();

      if (response.ok) {
        if (showToast) {
          this.showToast(result.message || 'Success!', 'success');
        }

        if (updateElement) {
          const el = document.getElementById(updateElement);
          if (el && result.html) {
            el.innerHTML = result.html;
          }
        }

        if (onSuccess) {
          onSuccess(result);
        }
      } else {
        throw new Error(result.message || 'Request failed');
      }
    } catch (error) {
      if (showToast) {
        this.showToast(error.message || 'An error occurred', 'error');
      }
      if (onError) {
        onError(error);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.removeAttribute('data-loading');
      }
    }
  },

  /**
   * Remove an element with confirmation
   * @param {string} elementId - The ID of the element to remove
   * @param {string} message - Confirmation message
   */
  async removeElement(elementId, message = 'Are you sure?') {
    if (!confirm(message)) return;

    const element = document.getElementById(elementId);
    if (!element) return;

    element.style.opacity = '0';
    element.style.transform = 'translateX(-20px)';
    element.style.transition = 'opacity .3s, transform .3s';

    setTimeout(() => element.remove(), 300);
  }
};

// Add CSS animation for spinning loader
if (!document.querySelector('style[data-admin-ajax]')) {
  const style = document.createElement('style');
  style.setAttribute('data-admin-ajax', 'true');
  style.textContent = `
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    @keyframes toastIn {
      from { opacity: 0; transform: translateY(-6px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `;
  document.head.appendChild(style);
}
