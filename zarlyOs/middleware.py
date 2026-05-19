import time

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from csp.middleware import CSPMiddleware
from csp.utils import build_policy

_SESSION_SKIP_PREFIXES = ('/admin/', '/static/', '/media/', '/favicon', '/robots', '/stripe/')


class SessionTimeoutMiddleware:
    """
    Enforces server-side inactivity timeout on all authenticated sessions.

    If an authenticated user has not made a request in SESSION_INACTIVITY_TIMEOUT
    seconds (default 3600), the session is flushed and the user is redirected to
    the appropriate login page.  AJAX/JSON requests receive a 401 instead so the
    browser can redirect programmatically rather than swallowing a redirect as data.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', 3600)

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not any(request.path.startswith(p) for p in _SESSION_SKIP_PREFIXES)
        ):
            now = time.time()
            last = request.session.get('_last_activity')

            if last is not None and (now - last) > self.timeout:
                role = getattr(request.user, 'role', None)
                login_url = 'customer_login' if role == 'customer' else 'admin_login'
                request.session.flush()

                login_path = reverse(login_url)
                is_ajax = (
                    request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    or 'application/json' in request.headers.get('Accept', '')
                )
                if is_ajax:
                    return JsonResponse({'session_expired': True, 'redirect': login_path}, status=401)

                messages.warning(request, 'Your session expired due to inactivity. Please log in again.')
                return redirect(login_path)

            request.session['_last_activity'] = now

        return self.get_response(request)


class EagerNonceCSPMiddleware(CSPMiddleware):
    """
    CSP middleware that forces nonce generation on every request.

    The upstream CSPMiddleware uses a SimpleLazyObject so the nonce is only
    generated (and inserted into the header) when something accesses
    request.csp_nonce.  For requests whose templates never touch the nonce
    the header would be emitted *without* a nonce, defeating the point.

    This subclass overrides build_policy to always evaluate the nonce so
    every response carries a matching nonce in both the CSP header and the
    template context.
    """

    def build_policy(self, request, response):
        # Force the lazy nonce to evaluate so _csp_nonce is always set.
        if hasattr(request, "csp_nonce"):
            # SimpleLazyObject must be coerced to a string to force evaluation.
            # Mere assignment returns the proxy object without evaluating it.
            str(request.csp_nonce)  # side-effect: calls _make_nonce, sets _csp_nonce
        config = getattr(response, "_csp_config", None)
        update = getattr(response, "_csp_update", None)
        replace = getattr(response, "_csp_replace", None)
        nonce = getattr(request, "_csp_nonce", None)
        return build_policy(config=config, update=update, replace=replace, nonce=nonce)
