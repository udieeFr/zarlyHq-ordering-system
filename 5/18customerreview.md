# Customer-Side Review — May 18, 2026

> **Scope:** `customers/` directory — security vulnerabilities + functionality completeness
> **Reviewed by:** Claude Code security agent
> **Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done

---

## Security Findings — All Fixed ✅

| # | Issue | Severity | Fixed |
|---|---|---|---|
| VULN 1 | Stored XSS in chat bubbles (`innerHTML` → `textContent`) | High | ✅ 2026-05-18 |
| VULN 2 | Missing `@customer_required` on all customer views | High | ✅ 2026-05-18 |
| VULN 3 | Unguarded `int(quantity)` → 500 + debug leak | Medium | ✅ 2026-05-18 |
| VULN 4 | PDF upload skips magic-byte content inspection | Medium | ✅ 2026-05-18 |
| VULN 5 | `AUTH_PASSWORD_VALIDATORS` disabled | Medium | ✅ 2026-05-18 |
| VULN 6 | Nominatim geocoding blocked by CSP (checkout map broken) | Medium | ✅ 2026-05-18 |

Tests: `tests/test_security_fixes.py`

---

## Functionality Findings — All Fixed ✅

| # | Feature | Fixed |
|---|---|---|
| FUNC 1 | Cart persistence on login | ✅ 2026-05-18 |
| FUNC 2 | Visual order timeline | ❌ Reverted |
| FUNC 3 | Post-delivery order rating (`OrderRating` model) | ✅ 2026-05-18 |
| FUNC 4 | Product reviews (`ProductReview` model) | ✅ 2026-05-18 |
| FUNC 5 | Promo / voucher codes | ❌ Reverted |
| FUNC 6 | Estimated delivery time | ❌ Reverted |
| FUNC 7 | Bank payment config → env vars | ✅ 2026-05-18 |

Tests: `tests/test_functionality_fixes.py`

---

## Pre-Production Config — Still Required

- [ ] Set `ALLOWED_HOSTS`
- [ ] Enable `SESSION_COOKIE_SECURE = True`
- [ ] Enable `CSRF_COOKIE_SECURE = True`
- [ ] Enable `SECURE_SSL_REDIRECT = True`
- [ ] Set env vars: `DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER`, `BANK_ACCOUNT_HOLDER`

---

## Remaining Gaps (out-of-scope for this sprint)

- Email verification on registration / OTP flow — no registration view exists yet
- Saved delivery addresses — partially covered by last-order auto-fill at checkout
