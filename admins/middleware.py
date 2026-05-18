SKIP_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/stripe/',
    '/favicon',
    '/robots',
)


class PageViewMiddleware:
    """Records a PageView row for every successful customer-facing GET request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.method == 'GET'
            and response.status_code == 200
            and not any(request.path.startswith(p) for p in SKIP_PREFIXES)
        ):
            try:
                from admins.models import PageView
                PageView.objects.create(
                    path=request.path,
                    user=request.user if request.user.is_authenticated else None,
                    session_key=request.session.session_key or '',
                    ip_address=self._get_ip(request),
                )
            except Exception:
                pass

        return response

    @staticmethod
    def _get_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
