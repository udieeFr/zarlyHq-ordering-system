"""
Step-up authentication (sudo mode).

A view decorated with @sudo_required will redirect unauthenticated users to a
password re-confirmation page. On success, a 15-minute window is stored in the
session so they are not prompted again on every page load.

Usage:
    @manager_required
    @sudo_required
    def sensitive_view(request): ...
"""
import time
import functools
from django.shortcuts import redirect

SUDO_SESSION_KEY = 'sudo_expires_at'
SUDO_NEXT_KEY = 'sudo_next'
SUDO_DURATION = 15 * 60  # seconds


def is_sudo_active(request):
    return time.time() < request.session.get(SUDO_SESSION_KEY, 0)


def grant_sudo(request):
    request.session[SUDO_SESSION_KEY] = time.time() + SUDO_DURATION


def sudo_required(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if is_sudo_active(request):
            return view_func(request, *args, **kwargs)
        request.session[SUDO_NEXT_KEY] = request.get_full_path()
        return redirect('sudo_confirm')
    return wrapper
