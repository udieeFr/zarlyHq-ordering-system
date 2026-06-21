import secrets
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

OTP_TTL = 300       # 5 minutes
MAX_ATTEMPTS = 5    # invalidate OTP after this many wrong guesses


def _cache_key(user_pk):
    return f'email_otp_{user_pk}'


def _attempts_key(user_pk):
    return f'email_otp_attempts_{user_pk}'


def generate_and_cache_otp(user):
    """Generate a cryptographically random 6-digit code and store it in cache."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_cache_key(user.pk), code, OTP_TTL)
    cache.delete(_attempts_key(user.pk))  # reset attempt counter on new code
    return code


def verify_otp(user, submitted_code):
    """
    Check a submitted OTP against the cached value.
    Returns: 'ok' | 'invalid' | 'expired'
    Deletes the cache entry on correct submission (single-use) or after MAX_ATTEMPTS.
    """
    key = _cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'

    att_key = _attempts_key(user.pk)
    attempts = (cache.get(att_key) or 0) + 1

    if stored != submitted_code:
        if attempts >= MAX_ATTEMPTS:
            cache.delete(key)
            cache.delete(att_key)
            return 'expired'
        cache.set(att_key, attempts, OTP_TTL)
        return 'invalid'

    cache.delete(key)
    cache.delete(att_key)
    return 'ok'


def mask_email(email):
    """e.g. johndoe@gmail.com -> j*****e@g****.com"""
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = local
    elif len(local) == 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]

    parts = domain.rsplit('.', 1)
    if len(parts) == 2:
        name, tld = parts
        masked_name = name[0] + '*' * max(1, len(name) - 1)
        masked_domain = f"{masked_name}.{tld}"
    else:
        masked_domain = domain

    return f"{masked_local}@{masked_domain}"


def send_verification_email(user, otp):
    """Send the 6-digit OTP to the user's email address."""
    try:
        body = render_to_string('emails/email_verification.html', {
            'username': user.username,
            'otp': otp,
        })
        send_mail(
            subject='Your ZarlyHQ verification code',
            message=f'Your verification code is: {otp}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[user.email],
            html_message=body,
        )
    except Exception as e:
        logger.warning(f'Could not send verification email to {user.email}: {e}')


def _signup_cache_key(email):
    return f'signup_otp:{email}'


def _signup_attempts_key(email):
    return f'signup_otp_attempts:{email}'


def generate_and_cache_signup_otp(email):
    """Generate a 6-digit OTP cached by email address (no user required)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_signup_cache_key(email), code, OTP_TTL)
    cache.delete(_signup_attempts_key(email))
    return code


def verify_signup_otp(email, submitted_code):
    """
    Verify a signup OTP keyed by email.
    Returns: 'ok' | 'invalid' | 'expired'
    Deletes cache on correct submission or after MAX_ATTEMPTS.
    """
    key = _signup_cache_key(email)
    stored = cache.get(key)
    if stored is None:
        return 'expired'

    att_key = _signup_attempts_key(email)
    attempts = (cache.get(att_key) or 0) + 1

    if stored != submitted_code:
        if attempts >= MAX_ATTEMPTS:
            cache.delete(key)
            cache.delete(att_key)
            return 'expired'
        cache.set(att_key, attempts, OTP_TTL)
        return 'invalid'

    cache.delete(key)
    cache.delete(att_key)
    return 'ok'


def send_signup_verification_email(username, email, otp):
    """Send OTP to an unregistered email address (no User object needed)."""
    try:
        body = render_to_string('emails/email_verification.html', {
            'username': username,
            'otp': otp,
        })
        send_mail(
            subject='Your ZarlyHQ verification code',
            message=f'Your verification code is: {otp}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[email],
            html_message=body,
        )
    except Exception as e:
        logger.warning(f'Could not send verification email to {email}: {e}')


# ── Password-change OTP (separate key prefix to avoid collisions) ─────────────

def _pw_change_cache_key(user_pk):
    return f'pw_change_otp_{user_pk}'


def _pw_change_attempts_key(user_pk):
    return f'pw_change_otp_attempts_{user_pk}'


def generate_and_cache_pw_change_otp(user):
    """Generate a 6-digit OTP for a password-change request and cache it."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_pw_change_cache_key(user.pk), code, OTP_TTL)
    cache.delete(_pw_change_attempts_key(user.pk))
    return code


def verify_pw_change_otp(user, submitted_code):
    """
    Verify a password-change OTP.
    Returns: 'ok' | 'invalid' | 'expired'
    Single-use; invalidated after MAX_ATTEMPTS wrong guesses.
    """
    key = _pw_change_cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'

    att_key = _pw_change_attempts_key(user.pk)
    attempts = (cache.get(att_key) or 0) + 1

    if stored != submitted_code:
        if attempts >= MAX_ATTEMPTS:
            cache.delete(key)
            cache.delete(att_key)
            return 'expired'
        cache.set(att_key, attempts, OTP_TTL)
        return 'invalid'

    cache.delete(key)
    cache.delete(att_key)
    return 'ok'


def send_pw_change_email(user, otp):
    """Send a password-change OTP to the user's registered email."""
    try:
        body = render_to_string('emails/email_verification.html', {
            'username': user.username,
            'otp': otp,
        })
        send_mail(
            subject='Your ZarlyHQ password change code',
            message=f'Your password change code is: {otp}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[user.email],
            html_message=body,
        )
    except Exception as e:
        logger.warning(f'Could not send password change email to {user.email}: {e}')


# ── Order confirmation OTP (separate key prefix — must not collide with email_otp_) ──

def _order_confirm_cache_key(user_pk):
    return f'order_confirm_otp_{user_pk}'


def _order_confirm_attempts_key(user_pk):
    return f'order_confirm_otp_attempts_{user_pk}'


def generate_and_cache_order_otp(user):
    """Generate a 6-digit OTP for order confirmation. Separate from email verification OTP."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_order_confirm_cache_key(user.pk), code, OTP_TTL)
    cache.delete(_order_confirm_attempts_key(user.pk))
    return code


def verify_order_otp(user, submitted_code):
    """
    Verify an order-confirmation OTP.
    Returns: 'ok' | 'invalid' | 'expired'
    Single-use; invalidated after MAX_ATTEMPTS wrong guesses.
    """
    key = _order_confirm_cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'

    att_key = _order_confirm_attempts_key(user.pk)
    attempts = (cache.get(att_key) or 0) + 1

    if stored != submitted_code:
        if attempts >= MAX_ATTEMPTS:
            cache.delete(key)
            cache.delete(att_key)
            return 'expired'
        cache.set(att_key, attempts, OTP_TTL)
        return 'invalid'

    cache.delete(key)
    cache.delete(att_key)
    return 'ok'


def send_order_confirmation_email(user, otp, order):
    """Send OTP with order summary so customer can confirm the exact contents."""
    try:
        items = list(order.items.select_related('product').all())
        send_mail(
            subject=f'Confirm your order #{order.id} — ZarlyHQ',
            message=(
                f'Hi {user.username},\n\n'
                f'Your confirmation code for Order #{order.id} is: {otp}\n'
                f'It expires in 5 minutes.\n\n'
                f'Order total: RM {order.total_amount}\n'
                f'Items: {", ".join(f"{i.product.name} x{i.quantity}" for i in items)}\n\n'
                f'Enter this code on the confirmation page to place your order.'
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as e:
        logger.warning(f'Could not send order confirmation email to {user.email}: {e}')
