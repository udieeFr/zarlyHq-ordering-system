from csp.middleware import CSPMiddleware
from csp.utils import build_policy


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
