# Support Chat (Encrypted Complaint Thread) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Fernet-encrypted, per-complaint support chat between customers and sales admins, with 1-req/min polling and Page Visibility API pause/resume.

**Architecture:** A `SupportMessage` model stores ciphertext in PostgreSQL; a thin `chat_crypto.py` module wraps Fernet encrypt/decrypt; two pairs of Django views (one admin, one customer) handle polling (GET) and sending (POST) via JSON; templates wire the UI with a JS polling loop.

**Tech Stack:** Django 6, Python `cryptography` (Fernet — already installed), `JsonResponse`, `django.test.Client` for tests, pytest-django.

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `admins/chat_crypto.py` | Fernet encrypt/decrypt helpers |
| Modify | `zarlyOs/settings.py` | Add `SUPPORT_CHAT_KEY` env var |
| Modify | `admins/models.py` | Add `SupportMessage` model; add `support_message_sent` to `AuditLog.ACTION_CHOICES` |
| Create | `admins/migrations/0024_supportmessage.py` | Generated migration |
| Modify | `admins/views.py` | Add `admin_complaint_messages` view; update `admin_complaint_detail` to pass initial messages |
| Modify | `admins/urls.py` | Wire admin messages endpoint |
| Modify | `customers/views.py` | Add `customer_complaint_detail` + `customer_complaint_messages` views |
| Modify | `customers/urls.py` | Add 2 customer URL patterns |
| Modify | `templates/admins/complaint_detail.html` | Add chat panel |
| Create | `templates/customers/complaint_detail.html` | New customer complaint detail + chat page |
| Modify | `templates/customers/customer_support.html` | Add "View Chat" link per complaint card |
| Create | `tests/test_support_chat.py` | All feature tests |

---

## Task 1: Add SUPPORT_CHAT_KEY to settings

**Files:**
- Modify: `zarlyOs/settings.py`

- [ ] **Step 1: Add setting**

  In `zarlyOs/settings.py`, after the `STRIPE_WEBHOOK_TOLERANCE` line, add:

  ```python
  # ============================================================================
  # SUPPORT CHAT
  # ============================================================================
  # Fernet 32-byte URL-safe base64 key. Generate once with:
  # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  SUPPORT_CHAT_KEY = os.getenv('SUPPORT_CHAT_KEY', '')
  ```

- [ ] **Step 2: Add to your `.env` file** (never commit)

  ```
  SUPPORT_CHAT_KEY=chz6Xd7HkrP1AZq3FLCymr1_tPW29rcVbdDuV-CaE2c=
  ```

  That value is an example — generate your own real key using the command in the comment above.

- [ ] **Step 3: Commit**

  ```bash
  git add zarlyOs/settings.py
  git commit -m "config: add SUPPORT_CHAT_KEY env var for chat encryption"
  ```

---

## Task 2: Encryption helper

**Files:**
- Create: `admins/chat_crypto.py`
- Create: `tests/test_support_chat.py`

- [ ] **Step 1: Write the failing test**

  Create `tests/test_support_chat.py`:

  ```python
  import pytest
  from django.test import override_settings, Client
  from django.urls import reverse
  from django.contrib.auth import get_user_model

  User = get_user_model()
  pytestmark = pytest.mark.django_db

  TEST_KEY = 'chz6Xd7HkrP1AZq3FLCymr1_tPW29rcVbdDuV-CaE2c='


  # ── Crypto ───────────────────────────────────────────────────────────────────

  @override_settings(SUPPORT_CHAT_KEY=TEST_KEY)
  class TestChatCrypto:
      def test_encrypt_decrypt_roundtrip(self):
          from admins.chat_crypto import encrypt_message, decrypt_message
          plaintext = "Hello, this is a secret message."
          assert decrypt_message(encrypt_message(plaintext)) == plaintext

      def test_encrypted_differs_from_plaintext(self):
          from admins.chat_crypto import encrypt_message
          assert encrypt_message("test") != "test"

      def test_decrypt_invalid_raises(self):
          from admins.chat_crypto import decrypt_message
          with pytest.raises(Exception):
              decrypt_message("notvalidciphertext")
  ```

- [ ] **Step 2: Run to confirm failure**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestChatCrypto -v
  ```

  Expected: `ModuleNotFoundError: No module named 'admins.chat_crypto'`

- [ ] **Step 3: Create `admins/chat_crypto.py`**

  ```python
  from cryptography.fernet import Fernet
  from django.conf import settings


  def _fernet() -> Fernet:
      key = settings.SUPPORT_CHAT_KEY
      if isinstance(key, str):
          key = key.encode()
      return Fernet(key)


  def encrypt_message(plaintext: str) -> str:
      return _fernet().encrypt(plaintext.encode()).decode()


  def decrypt_message(ciphertext: str) -> str:
      return _fernet().decrypt(ciphertext.encode()).decode()
  ```

- [ ] **Step 4: Run to confirm pass**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestChatCrypto -v
  ```

  Expected: 3 PASSED

- [ ] **Step 5: Commit**

  ```bash
  git add admins/chat_crypto.py tests/test_support_chat.py
  git commit -m "feat: add Fernet encryption helper for support chat"
  ```

---

## Task 3: SupportMessage model + AuditLog action type

**Files:**
- Modify: `admins/models.py`
- Modify: `tests/test_support_chat.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_support_chat.py`)

  ```python
  # ── Model ────────────────────────────────────────────────────────────────────

  @override_settings(SUPPORT_CHAT_KEY=TEST_KEY)
  class TestSupportMessageModel:
      def _make_complaint(self):
          from admins.models import Order, Complaint
          from customers.models import Category
          Category.objects.get_or_create(name='Chat Test Cat')
          customer = User.objects.create_user(
              username='chatcust', email='chatcust@t.com', password='pass', role='customer'
          )
          order = Order.objects.create(customer=customer, total_amount=100, status='delivered')
          return Complaint.objects.create(order=order, customer=customer, subject='Test', message='Msg')

      def test_ordering_oldest_first(self):
          from admins.models import SupportMessage
          complaint = self._make_complaint()
          admin = User.objects.create_user(
              username='chatadmin1', email='ca1@t.com', password='pass', role='sales_admin'
          )
          m1 = SupportMessage.objects.create(complaint=complaint, sender=admin, body='first')
          m2 = SupportMessage.objects.create(complaint=complaint, sender=admin, body='second')
          msgs = list(SupportMessage.objects.filter(complaint=complaint))
          assert msgs[0].pk == m1.pk
          assert msgs[1].pk == m2.pk

      def test_is_read_defaults_false(self):
          from admins.models import SupportMessage
          complaint = self._make_complaint()
          admin = User.objects.create_user(
              username='chatadmin2', email='ca2@t.com', password='pass', role='sales_admin'
          )
          msg = SupportMessage.objects.create(complaint=complaint, sender=admin, body='hi')
          assert msg.is_read is False

      def test_complaint_created_at_index_declared(self):
          from admins.models import SupportMessage
          index_fields = [
              tuple(f.lstrip('-') for f in idx.fields)
              for idx in SupportMessage._meta.indexes
          ]
          assert ('complaint', 'created_at') in index_fields

      def test_support_message_sent_is_valid_audit_action(self):
          from admins.models import AuditLog
          valid_actions = [a[0] for a in AuditLog.ACTION_CHOICES]
          assert 'support_message_sent' in valid_actions
  ```

- [ ] **Step 2: Run to confirm failure**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestSupportMessageModel -v
  ```

  Expected: `ImportError` or `AttributeError` — `SupportMessage` does not exist yet.

- [ ] **Step 3: Add `SupportMessage` to `admins/models.py`**

  Insert after the `Complaint` class (before `PrepGroup`):

  ```python
  class SupportMessage(models.Model):
      complaint  = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='messages')
      sender     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
      body       = models.TextField()  # Fernet-encrypted ciphertext
      created_at = models.DateTimeField(auto_now_add=True, db_index=True)
      is_read    = models.BooleanField(default=False)

      class Meta:
          ordering = ['created_at']
          indexes  = [
              models.Index(fields=['complaint', 'created_at']),
          ]
  ```

- [ ] **Step 4: Add `support_message_sent` to `AuditLog.ACTION_CHOICES`**

  In `AuditLog.ACTION_CHOICES`, append (before the closing parenthesis):

  ```python
  ('support_message_sent', 'Support Message Sent'),
  ```

- [ ] **Step 5: Run to confirm pass**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestSupportMessageModel -v
  ```

  Expected: 4 PASSED

- [ ] **Step 6: Commit**

  ```bash
  git add admins/models.py tests/test_support_chat.py
  git commit -m "feat: add SupportMessage model and support_message_sent audit action"
  ```

---

## Task 4: Generate and apply migration

**Files:**
- Create: `admins/migrations/0024_supportmessage.py` (auto-generated)

- [ ] **Step 1: Run makemigrations**

  ```
  venv\Scripts\python.exe manage.py makemigrations admins --name supportmessage
  ```

  Expected: `admins/migrations/0024_supportmessage.py` created.

- [ ] **Step 2: Apply migration**

  ```
  venv\Scripts\python.exe manage.py migrate
  ```

  Expected: Applies cleanly with no errors.

- [ ] **Step 3: Confirm all existing tests still pass**

  ```
  venv\Scripts\python.exe -m pytest tests/ -v
  ```

  Expected: All tests pass.

- [ ] **Step 4: Commit**

  ```bash
  git add admins/migrations/0024_supportmessage.py
  git commit -m "migration: add SupportMessage table"
  ```

---

## Task 5: Admin endpoints + URLs

**Files:**
- Modify: `admins/views.py`
- Modify: `admins/urls.py`
- Modify: `tests/test_support_chat.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_support_chat.py`)

  ```python
  # ── Admin endpoints ───────────────────────────────────────────────────────────

  @pytest.mark.django_db
  @override_settings(SUPPORT_CHAT_KEY=TEST_KEY)
  class TestAdminComplaintMessages:
      def setup_method(self):
          from admins.models import Order, Complaint
          self.client = Client()
          self.customer = User.objects.create_user(
              username='acm_cust', email='acm_c@t.com', password='pass', role='customer'
          )
          self.admin = User.objects.create_user(
              username='acm_admin', email='acm_a@t.com', password='pass', role='sales_admin'
          )
          order = Order.objects.create(customer=self.customer, total_amount=100, status='delivered')
          self.complaint = Complaint.objects.create(
              order=order, customer=self.customer, subject='S', message='M'
          )

      def _url(self):
          return reverse('admin_complaint_messages', args=[self.complaint.id])

      def test_unauthenticated_redirects(self):
          r = self.client.get(self._url())
          assert r.status_code == 302

      def test_customer_cannot_access(self):
          self.client.force_login(self.customer)
          r = self.client.get(self._url())
          assert r.status_code in (302, 403)

      def test_admin_get_returns_json(self):
          self.client.force_login(self.admin)
          r = self.client.get(self._url())
          assert r.status_code == 200
          data = r.json()
          assert 'messages' in data
          assert 'locked' in data
          assert data['locked'] is False

      def test_admin_post_creates_message(self):
          from admins.models import SupportMessage
          self.client.force_login(self.admin)
          r = self.client.post(self._url(), {'body': 'Hello customer'})
          assert r.status_code == 200
          assert r.json()['ok'] is True
          assert SupportMessage.objects.filter(complaint=self.complaint).count() == 1

      def test_post_empty_body_returns_400(self):
          self.client.force_login(self.admin)
          r = self.client.post(self._url(), {'body': ''})
          assert r.status_code == 400

      def test_post_locked_when_resolved(self):
          from admins.models import Complaint
          Complaint.objects.filter(pk=self.complaint.pk).update(status='resolved')
          self.client.force_login(self.admin)
          r = self.client.post(self._url(), {'body': 'too late'})
          assert r.status_code == 403

      def test_since_filter_returns_only_new(self):
          from admins.models import SupportMessage
          from django.utils import timezone
          self.client.force_login(self.admin)
          SupportMessage.objects.create(complaint=self.complaint, sender=self.admin, body='old')
          cutoff = timezone.now().isoformat()
          SupportMessage.objects.create(complaint=self.complaint, sender=self.admin, body='new')
          r = self.client.get(self._url() + f'?since={cutoff}')
          data = r.json()
          assert len(data['messages']) == 1

      def test_audit_log_created_on_send(self):
          from admins.models import AuditLog
          self.client.force_login(self.admin)
          self.client.post(self._url(), {'body': 'audit this'})
          assert AuditLog.objects.filter(action_type='support_message_sent').exists()
  ```

- [ ] **Step 2: Run to confirm failure**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestAdminComplaintMessages -v
  ```

  Expected: `NoReverseMatch` for `admin_complaint_messages`.

- [ ] **Step 3: Add `SupportMessage` to the import line in `admins/views.py`**

  Change:
  ```python
  from .models import Order, OrderItem, DigitalSignature, Complaint, PrepGroup, Payment, AuditLog, Notification, OrderEvent
  ```
  To:
  ```python
  from .models import Order, OrderItem, DigitalSignature, Complaint, PrepGroup, Payment, AuditLog, Notification, OrderEvent, SupportMessage
  ```

- [ ] **Step 4: Replace `admin_complaint_detail` in `admins/views.py`**

  Find the existing `admin_complaint_detail` function and replace it:

  ```python
  @sales_admin_required
  def admin_complaint_detail(request, complaint_id):
      """Detailed view for specific complaint validation."""
      from admins.chat_crypto import decrypt_message
      complaint = get_object_or_404(Complaint, id=complaint_id)
      raw_msgs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
      initial_messages = []
      for msg in raw_msgs:
          try:
              body = decrypt_message(msg.body)
          except Exception:
              body = '[encrypted]'
          initial_messages.append({
              'sender': msg.sender.username if msg.sender else 'deleted',
              'body': body,
              'created_at': msg.created_at.strftime('%d %b %Y, %H:%M'),
              'is_mine': msg.sender_id == request.user.id,
          })
      return render(request, 'admins/complaint_detail.html', {
          'complaint': complaint,
          'order': complaint.order,
          'customer': complaint.customer,
          'initial_messages': initial_messages,
      })
  ```

- [ ] **Step 5: Append `admin_complaint_messages` view to `admins/views.py`** (after `resolve_complaint`)

  ```python
  @sales_admin_required
  def admin_complaint_messages(request, complaint_id):
      """Poll for or send support chat messages (admin side)."""
      from admins.chat_crypto import encrypt_message, decrypt_message
      from django.utils.dateparse import parse_datetime

      complaint = get_object_or_404(Complaint, id=complaint_id)

      if request.method == 'GET':
          since_raw = request.GET.get('since')
          qs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
          if since_raw:
              since_dt = parse_datetime(since_raw)
              if since_dt:
                  qs = qs.filter(created_at__gt=since_dt)
          msgs = []
          for msg in qs:
              try:
                  body = decrypt_message(msg.body)
              except Exception:
                  body = '[encrypted]'
              msgs.append({
                  'id': msg.id,
                  'sender': msg.sender.username if msg.sender else 'deleted',
                  'body': body,
                  'created_at': msg.created_at.isoformat(),
                  'is_mine': msg.sender_id == request.user.id,
              })
          return JsonResponse({'messages': msgs, 'locked': complaint.status == 'resolved'})

      if request.method == 'POST':
          if complaint.status == 'resolved':
              return JsonResponse({'error': 'Chat is locked'}, status=403)
          body = request.POST.get('body', '').strip()
          if not body:
              return JsonResponse({'error': 'Message cannot be empty'}, status=400)
          SupportMessage.objects.create(
              complaint=complaint,
              sender=request.user,
              body=encrypt_message(body),
          )
          log_audit(request, 'support_message_sent', target=complaint,
                    description=f'Admin sent support message on Complaint #{complaint.id}')
          return JsonResponse({'ok': True})

      return JsonResponse({'error': 'Method not allowed'}, status=405)
  ```

- [ ] **Step 6: Add URL to `admins/urls.py`** (after the `resolve_complaint` line)

  ```python
  path('complaints/<int:complaint_id>/messages/', views.admin_complaint_messages, name='admin_complaint_messages'),
  ```

- [ ] **Step 7: Run tests**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestAdminComplaintMessages -v
  ```

  Expected: 8 PASSED

- [ ] **Step 8: Commit**

  ```bash
  git add admins/views.py admins/urls.py tests/test_support_chat.py
  git commit -m "feat: admin complaint messages poll and send endpoints"
  ```

---

## Task 6: Customer endpoints + URLs

**Files:**
- Modify: `customers/views.py`
- Modify: `customers/urls.py`
- Modify: `tests/test_support_chat.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_support_chat.py`)

  ```python
  # ── Customer endpoints ────────────────────────────────────────────────────────

  @pytest.mark.django_db
  @override_settings(SUPPORT_CHAT_KEY=TEST_KEY)
  class TestCustomerComplaintMessages:
      def setup_method(self):
          from admins.models import Order, Complaint
          self.client = Client()
          self.customer = User.objects.create_user(
              username='ccm_cust', email='ccm_c@t.com', password='pass', role='customer'
          )
          self.other = User.objects.create_user(
              username='ccm_other', email='ccm_o@t.com', password='pass', role='customer'
          )
          self.admin = User.objects.create_user(
              username='ccm_admin', email='ccm_a@t.com', password='pass', role='sales_admin'
          )
          order = Order.objects.create(customer=self.customer, total_amount=100, status='delivered')
          self.complaint = Complaint.objects.create(
              order=order, customer=self.customer, subject='S', message='M'
          )

      def _detail_url(self):
          return reverse('customer_complaint_detail', args=[self.complaint.id])

      def _msg_url(self):
          return reverse('customer_complaint_messages', args=[self.complaint.id])

      def test_detail_unauthenticated_redirects(self):
          r = self.client.get(self._detail_url())
          assert r.status_code == 302

      def test_detail_other_customer_gets_404(self):
          self.client.force_login(self.other)
          r = self.client.get(self._detail_url())
          assert r.status_code == 404

      def test_detail_owner_gets_200(self):
          self.client.force_login(self.customer)
          r = self.client.get(self._detail_url())
          assert r.status_code == 200

      def test_messages_other_customer_gets_404(self):
          self.client.force_login(self.other)
          r = self.client.get(self._msg_url())
          assert r.status_code == 404

      def test_messages_owner_get_returns_json(self):
          self.client.force_login(self.customer)
          r = self.client.get(self._msg_url())
          assert r.status_code == 200
          data = r.json()
          assert 'messages' in data
          assert 'locked' in data

      def test_customer_post_creates_message(self):
          from admins.models import SupportMessage
          self.client.force_login(self.customer)
          r = self.client.post(self._msg_url(), {'body': 'Please help!'})
          assert r.status_code == 200
          assert r.json()['ok'] is True
          assert SupportMessage.objects.filter(complaint=self.complaint).count() == 1

      def test_post_empty_body_returns_400(self):
          self.client.force_login(self.customer)
          r = self.client.post(self._msg_url(), {'body': ''})
          assert r.status_code == 400

      def test_post_locked_when_resolved(self):
          from admins.models import Complaint
          Complaint.objects.filter(pk=self.complaint.pk).update(status='resolved')
          self.client.force_login(self.customer)
          r = self.client.post(self._msg_url(), {'body': 'too late'})
          assert r.status_code == 403

      def test_audit_log_created_on_send(self):
          from admins.models import AuditLog
          self.client.force_login(self.customer)
          self.client.post(self._msg_url(), {'body': 'audit this'})
          assert AuditLog.objects.filter(action_type='support_message_sent').exists()

      def test_messages_decrypted_in_response(self):
          from admins.models import SupportMessage
          from admins.chat_crypto import encrypt_message
          SupportMessage.objects.create(
              complaint=self.complaint,
              sender=self.customer,
              body=encrypt_message('decrypted text'),
          )
          self.client.force_login(self.customer)
          r = self.client.get(self._msg_url())
          bodies = [m['body'] for m in r.json()['messages']]
          assert 'decrypted text' in bodies
  ```

- [ ] **Step 2: Run to confirm failure**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestCustomerComplaintMessages -v
  ```

  Expected: `NoReverseMatch` for `customer_complaint_detail` / `customer_complaint_messages`.

- [ ] **Step 3: Append views to `customers/views.py`**

  ```python
  @login_required
  def customer_complaint_detail(request, complaint_id):
      """Customer view of their own complaint with chat thread."""
      from admins.models import Complaint
      complaint = get_object_or_404(Complaint, id=complaint_id, customer=request.user)
      return render(request, 'customers/complaint_detail.html', {
          'complaint': complaint,
          'order': complaint.order,
          'locked': complaint.status == 'resolved',
      })


  @login_required
  def customer_complaint_messages(request, complaint_id):
      """Poll for or send support chat messages (customer side)."""
      from admins.models import Complaint, SupportMessage
      from admins.chat_crypto import encrypt_message, decrypt_message
      from django.utils.dateparse import parse_datetime

      complaint = get_object_or_404(Complaint, id=complaint_id, customer=request.user)

      if request.method == 'GET':
          since_raw = request.GET.get('since')
          qs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
          if since_raw:
              since_dt = parse_datetime(since_raw)
              if since_dt:
                  qs = qs.filter(created_at__gt=since_dt)
          msgs = []
          for msg in qs:
              try:
                  body = decrypt_message(msg.body)
              except Exception:
                  body = '[encrypted]'
              msgs.append({
                  'id': msg.id,
                  'sender': msg.sender.username if msg.sender else 'deleted',
                  'body': body,
                  'created_at': msg.created_at.isoformat(),
                  'is_mine': msg.sender_id == request.user.id,
              })
          return JsonResponse({'messages': msgs, 'locked': complaint.status == 'resolved'})

      if request.method == 'POST':
          if complaint.status == 'resolved':
              return JsonResponse({'error': 'Chat is locked'}, status=403)
          body = request.POST.get('body', '').strip()
          if not body:
              return JsonResponse({'error': 'Message cannot be empty'}, status=400)
          SupportMessage.objects.create(
              complaint=complaint,
              sender=request.user,
              body=encrypt_message(body),
          )
          log_audit(request, 'support_message_sent', target=complaint,
                    description=f'Customer sent support message on Complaint #{complaint.id}')
          return JsonResponse({'ok': True})

      return JsonResponse({'error': 'Method not allowed'}, status=405)
  ```

- [ ] **Step 4: Add 2 URL patterns to `customers/urls.py`** (after the `support/` line)

  ```python
  path('support/complaint/<int:complaint_id>/', views.customer_complaint_detail, name='customer_complaint_detail'),
  path('support/complaint/<int:complaint_id>/messages/', views.customer_complaint_messages, name='customer_complaint_messages'),
  ```

- [ ] **Step 5: Run tests**

  ```
  venv\Scripts\python.exe -m pytest tests/test_support_chat.py::TestCustomerComplaintMessages -v
  ```

  Expected: 10 PASSED

- [ ] **Step 6: Run full suite**

  ```
  venv\Scripts\python.exe -m pytest tests/ -v
  ```

  Expected: All tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add customers/views.py customers/urls.py tests/test_support_chat.py
  git commit -m "feat: customer complaint detail and messages endpoints"
  ```

---

## Task 7: Admin chat panel template

**Files:**
- Modify: `templates/admins/complaint_detail.html`

- [ ] **Step 1: Add the chat panel**

  In `templates/admins/complaint_detail.html`, insert the following block **immediately before `{% endblock %}`**:

  ```html
  <!-- ── Support Chat Panel ──────────────────────────────── -->
  <div class="row mt-4">
      <div class="col-12">
          <div class="content-card">
              <h5 class="fw-bold border-bottom pb-3 mb-3">💬 Support Chat</h5>

              {% if complaint.status == 'resolved' %}
              <div class="alert alert-secondary small mb-3">🔒 This complaint is resolved. Chat is read-only.</div>
              {% endif %}

              <div id="chat-thread" style="max-height:380px; overflow-y:auto; padding-right:4px; margin-bottom:1rem;">
                  {% for msg in initial_messages %}
                  <div class="d-flex {% if msg.is_mine %}justify-content-end{% endif %} mb-2">
                      <div class="p-2 px-3 rounded-3 small"
                           style="max-width:75%; {% if msg.is_mine %}background:#fff7ed; border:1px solid #fb923c;{% else %}background:#f1f5f9; border:1px solid #cbd5e1;{% endif %}">
                          <div class="fw-semibold" style="font-size:0.72rem; color:#64748b; margin-bottom:2px;">
                              {{ msg.sender }}{% if msg.is_mine %} (you){% endif %} · {{ msg.created_at }}
                          </div>
                          <div>{{ msg.body }}</div>
                      </div>
                  </div>
                  {% empty %}
                  <p class="text-muted small text-center" id="empty-msg">No messages yet. Start the conversation.</p>
                  {% endfor %}
              </div>

              {% if complaint.status != 'resolved' %}
              <form id="chat-form" class="d-flex gap-2">
                  {% csrf_token %}
                  <input type="text" id="chat-input" class="form-control form-control-sm"
                         placeholder="Type a message…" autocomplete="off">
                  <button type="submit" class="btn btn-sm btn-warning fw-bold px-3">Send</button>
              </form>
              {% endif %}
          </div>
      </div>
  </div>

  <script>
  (function () {
      const MESSAGES_URL = "{% url 'admin_complaint_messages' complaint.id %}";
      const CSRF = document.cookie.replace(/(?:(?:^|.*;\s*)csrftoken\s*=\s*([^;]*).*$)|^.*$/, '$1');
      const thread = document.getElementById('chat-thread');
      const form   = document.getElementById('chat-form');
      const input  = document.getElementById('chat-input');
      let lastSeen = null;

      function appendMessage(msg) {
          const emptyMsg = document.getElementById('empty-msg');
          if (emptyMsg) emptyMsg.remove();
          const wrap = document.createElement('div');
          wrap.className = 'd-flex ' + (msg.is_mine ? 'justify-content-end' : '') + ' mb-2';
          const style = msg.is_mine
              ? 'background:#fff7ed;border:1px solid #fb923c;'
              : 'background:#f1f5f9;border:1px solid #cbd5e1;';
          wrap.innerHTML = `<div class="p-2 px-3 rounded-3 small" style="max-width:75%;${style}">
              <div class="fw-semibold" style="font-size:0.72rem;color:#64748b;margin-bottom:2px;">
                  ${msg.sender}${msg.is_mine ? ' (you)' : ''}
              </div>
              <div>${msg.body}</div>
          </div>`;
          thread.appendChild(wrap);
          lastSeen = msg.created_at;
          thread.scrollTop = thread.scrollHeight;
      }

      function poll() {
          const url = lastSeen ? MESSAGES_URL + '?since=' + encodeURIComponent(lastSeen) : MESSAGES_URL;
          fetch(url).then(r => r.json()).then(data => {
              data.messages.forEach(appendMessage);
              if (data.locked && form) form.style.display = 'none';
          });
      }

      if (form) {
          form.addEventListener('submit', function (e) {
              e.preventDefault();
              const body = input.value.trim();
              if (!body) return;
              input.value = '';
              fetch(MESSAGES_URL, {
                  method: 'POST',
                  headers: {'X-CSRFToken': CSRF, 'Content-Type': 'application/x-www-form-urlencoded'},
                  body: 'body=' + encodeURIComponent(body),
              }).then(r => r.json()).then(data => { if (data.ok) poll(); });
          });
      }

      let pollTimer;
      function startPolling() { pollTimer = setInterval(poll, 60000); }
      function stopPolling()  { clearInterval(pollTimer); }
      document.addEventListener('visibilitychange', () => document.hidden ? stopPolling() : startPolling());

      thread.scrollTop = thread.scrollHeight;
      startPolling();
  })();
  </script>
  ```

- [ ] **Step 2: Manually verify**

  Start dev server: `venv\Scripts\python.exe manage.py runserver`

  Log in as a sales admin, navigate to `/dashboard/complaints/<id>/`, confirm the chat panel appears and "Send" works.

- [ ] **Step 3: Commit**

  ```bash
  git add templates/admins/complaint_detail.html admins/views.py
  git commit -m "feat: add chat panel to admin complaint detail page"
  ```

---

## Task 8: Customer complaint detail template + support list link

**Files:**
- Create: `templates/customers/complaint_detail.html`
- Modify: `templates/customers/customer_support.html`

- [ ] **Step 1: Create `templates/customers/complaint_detail.html`**

  ```html
  {% extends 'base.html' %}

  {% block page_title %}Complaint #{{ complaint.id }} — Zarly BigFood{% endblock %}

  {% block content %}
  <style>
    .chat-thread { max-height: 420px; overflow-y: auto; padding: 0.5rem 0; }
    .chat-bubble { max-width: 75%; border-radius: 1rem; padding: 0.55rem 0.85rem; font-size: 0.88rem; line-height: 1.5; }
    .bubble-mine   { background: var(--brand-light); border: 1px solid var(--brand-border); margin-left: auto; }
    .bubble-theirs { background: #f1f5f9; border: 1px solid #cbd5e1; }
    .bubble-meta { font-size: 0.72rem; color: var(--muted); margin-bottom: 3px; }
    .chat-input-row { display: flex; gap: 0.5rem; margin-top: 1rem; }
    .chat-input-row input  { flex: 1; border-radius: var(--radius-sm); border: 1px solid var(--border); padding: 0.55rem 0.85rem; font-size: 0.9rem; }
    .chat-input-row button { border-radius: var(--radius-sm); background: var(--brand); border: none; color: #fff; font-weight: 700; padding: 0 1.1rem; cursor: pointer; }
    .chat-input-row button:hover { background: var(--brand-dark); }
  </style>

  <div style="padding: 1.75rem 0 3rem;">
      <div class="mb-3">
          <a href="{% url 'customer_support' %}" style="color:var(--brand-dark); font-weight:600;">← Back to Support</a>
      </div>

      <h2 style="font-size:1.3rem; font-weight:800; margin-bottom:0.25rem;">Complaint #{{ complaint.id }}</h2>
      <p style="color:var(--muted); font-size:0.875rem; margin-bottom:1.5rem;">Order #{{ order.id }} · {{ complaint.created_at|date:"N j, Y" }}</p>

      <div style="display:grid; gap:1rem;">

          <!-- Complaint summary -->
          <div style="background:#fff; border:1px solid var(--border); border-radius:var(--radius); padding:1rem 1.1rem; box-shadow:var(--shadow-sm);">
              <div style="font-weight:700; margin-bottom:0.3rem;">{{ complaint.subject }}</div>
              <div style="color:var(--dark-3); font-size:0.88rem; margin-bottom:0.75rem;">{{ complaint.message }}</div>
              {% if complaint.status == 'resolved' %}
              <span style="background:var(--success-bg); color:#065f46; border:1px solid #a7f3d0; border-radius:999px; padding:0.2rem 0.65rem; font-size:0.75rem; font-weight:700;">✅ Resolved</span>
              {% else %}
              <span style="background:var(--warning-bg); color:#92400e; border:1px solid #fde68a; border-radius:999px; padding:0.2rem 0.65rem; font-size:0.75rem; font-weight:700;">⏳ Pending</span>
              {% endif %}
              {% if complaint.resolution_note %}
              <div style="margin-top:0.75rem; padding:0.65rem 0.85rem; background:var(--brand-light); border:1px solid var(--brand-border); border-radius:var(--radius-sm);">
                  <span style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#c2410c; display:block; margin-bottom:0.25rem;">From Zarly team:</span>
                  <p style="font-size:0.875rem; margin:0;">{{ complaint.resolution_note }}</p>
              </div>
              {% endif %}
          </div>

          <!-- Chat thread -->
          <div style="background:#fff; border:1px solid var(--border); border-radius:var(--radius); padding:1rem 1.1rem; box-shadow:var(--shadow-sm);">
              <div style="font-weight:700; font-size:0.95rem; margin-bottom:0.85rem; padding-bottom:0.65rem; border-bottom:1px solid var(--border);">💬 Support Chat</div>

              {% if locked %}
              <div style="font-size:0.8rem; color:var(--muted); margin-bottom:0.75rem;">🔒 This complaint is resolved. Chat is read-only.</div>
              {% endif %}

              <div class="chat-thread" id="chat-thread">
                  <p class="text-muted text-center" style="font-size:0.85rem; margin:1rem 0;" id="empty-msg">Loading…</p>
              </div>

              {% if not locked %}
              <form class="chat-input-row" id="chat-form">
                  {% csrf_token %}
                  <input type="text" id="chat-input" placeholder="Type a message…" autocomplete="off">
                  <button type="submit">Send</button>
              </form>
              {% endif %}
          </div>

      </div>
  </div>

  <script>
  (function () {
      const MESSAGES_URL = "{% url 'customer_complaint_messages' complaint.id %}";
      const CSRF    = document.cookie.replace(/(?:(?:^|.*;\s*)csrftoken\s*=\s*([^;]*).*$)|^.*$/, '$1');
      const thread  = document.getElementById('chat-thread');
      const emptyMsg = document.getElementById('empty-msg');
      const form    = document.getElementById('chat-form');
      const input   = document.getElementById('chat-input');
      const locked  = {{ locked|yesno:"true,false" }};
      let lastSeen  = null;
      let hasMessages = false;

      function appendMessage(msg) {
          if (!hasMessages && emptyMsg) emptyMsg.remove();
          hasMessages = true;
          const wrap = document.createElement('div');
          wrap.style.cssText = 'display:flex; margin-bottom:0.5rem;' + (msg.is_mine ? 'justify-content:flex-end;' : '');
          const cls = msg.is_mine ? 'chat-bubble bubble-mine' : 'chat-bubble bubble-theirs';
          wrap.innerHTML = `<div class="${cls}">
              <div class="bubble-meta">${msg.is_mine ? 'You' : 'Support team'}</div>
              <div>${msg.body}</div>
          </div>`;
          thread.appendChild(wrap);
          lastSeen = msg.created_at;
          thread.scrollTop = thread.scrollHeight;
      }

      function poll() {
          const url = lastSeen ? MESSAGES_URL + '?since=' + encodeURIComponent(lastSeen) : MESSAGES_URL;
          fetch(url).then(r => r.json()).then(data => {
              if (!hasMessages && data.messages.length === 0 && emptyMsg) {
                  emptyMsg.textContent = 'No messages yet. Start the conversation.';
              }
              data.messages.forEach(appendMessage);
              if (data.locked && form) form.style.display = 'none';
          });
      }

      if (form) {
          form.addEventListener('submit', function (e) {
              e.preventDefault();
              const body = input.value.trim();
              if (!body) return;
              input.value = '';
              fetch(MESSAGES_URL, {
                  method: 'POST',
                  headers: {'X-CSRFToken': CSRF, 'Content-Type': 'application/x-www-form-urlencoded'},
                  body: 'body=' + encodeURIComponent(body),
              }).then(r => r.json()).then(data => { if (data.ok) poll(); });
          });
      }

      let pollTimer;
      function startPolling() { pollTimer = setInterval(poll, 60000); }
      function stopPolling()  { clearInterval(pollTimer); }
      document.addEventListener('visibilitychange', () => document.hidden ? stopPolling() : startPolling());

      if (!locked) startPolling();
      poll();
  })();
  </script>
  {% endblock %}
  ```

- [ ] **Step 2: Add "View Chat" link to each complaint card in `templates/customers/customer_support.html`**

  Find the line containing `<div class="support-message">{{ c.message }}</div>` and add immediately after it:

  ```html
  <div style="margin-bottom:0.5rem;">
      <a href="{% url 'customer_complaint_detail' c.id %}" style="font-size:0.82rem; font-weight:700; color:var(--brand-dark);">💬 View Chat</a>
  </div>
  ```

- [ ] **Step 3: Manually verify**

  Log in as a customer, go to `/support/`, click "View Chat" on a complaint card. The detail page should load, show the complaint summary, and the chat thread (loading state then empty state).

  Send a message — it should appear immediately. Switch to a new tab with the admin complaint detail — the message should be visible there too.

- [ ] **Step 4: Commit**

  ```bash
  git add templates/customers/complaint_detail.html templates/customers/customer_support.html
  git commit -m "feat: customer complaint detail page and chat UI"
  ```

---

## Task 9: Full test run

- [ ] **Step 1: Run all tests**

  ```
  venv\Scripts\python.exe -m pytest tests/ -v
  ```

  Expected: All tests pass, including the ~23 new support chat tests.

- [ ] **Step 2: Fix any failures before marking done.**

---

## Self-Review

**Spec coverage:**
- ✅ `SupportMessage` model — complaint FK, sender FK, encrypted body, created_at (db_index), is_read, ordering, composite index
- ✅ Fernet symmetric encryption at rest; key in `SUPPORT_CHAT_KEY` env var
- ✅ Access control — only `complaint.customer` (customer side) or `sales_admin`/`manager` (admin side) can read/write
- ✅ Polling 1 req/min, Page Visibility API pause/resume
- ✅ `?since=<ts>` filter so polls only fetch new messages
- ✅ Chat locked (read-only, POST returns 403) when `complaint.status == 'resolved'`
- ✅ AuditLog entry on every send (`support_message_sent`)
- ✅ Customer URL: `/support/complaint/<id>/` (new page, no existing detail page was modified)
- ✅ Admin URL: panel appended to existing `admins/complaint_detail.html`
- ✅ NOT in scope: WebSockets, SSE, attachments, admin↔admin chat, E2E encryption — none added

**Placeholder scan:** No TBD, TODO, incomplete sections.

**Type consistency:** `SupportMessage`, `admin_complaint_messages`, `customer_complaint_detail`, `customer_complaint_messages` — names used consistently across model / views / urls / templates / tests.
