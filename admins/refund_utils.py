"""
Refund and remake order utilities.

issue_stripe_refund  — attempt an automatic Stripe refund and record the result.
process_refund       — high-level helper used by both reject_order and resolve_complaint.
remake_order         — clone a completed order back into approved state with priority.
"""
import os
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def issue_stripe_refund(payment):
    """
    Call the Stripe Refunds API against a payment record.

    Returns (success: bool, stripe_refund_id_or_error: str).
    """
    import stripe
    from django.conf import settings
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        kwargs = {}
        if payment.stripe_charge_id:
            kwargs['charge'] = payment.stripe_charge_id
        elif payment.stripe_payment_intent_id:
            kwargs['payment_intent'] = payment.stripe_payment_intent_id
        else:
            return False, 'No Stripe charge or payment_intent ID on record'

        refund = stripe.Refund.create(**kwargs)
        return True, refund.id

    except stripe.error.InvalidRequestError as e:
        # Already refunded or charge not found
        return False, f'Stripe InvalidRequestError: {e}'
    except stripe.error.StripeError as e:
        return False, f'Stripe error: {e}'
    except Exception as e:
        return False, f'Unexpected error: {e}'


def process_refund(order, source, request=None, complaint=None):
    """
    Attempt a refund for an order.

    - If a succeeded Stripe payment exists → auto-refund via API.
    - Otherwise → create a manual Refund record for the manager.

    Returns the Refund instance.
    """
    from admins.models import Payment, Refund
    from admins.notifications import log_audit, notify

    actor = getattr(request, 'user', None) if request else None

    stripe_payment = order.payments.filter(
        payment_method='stripe',
        status='succeeded',
    ).first()

    if stripe_payment:
        success, result = issue_stripe_refund(stripe_payment)

        if success:
            stripe_payment.status = 'refunded'
            stripe_payment.save(update_fields=['status'])

            refund = Refund.objects.create(
                order=order,
                payment=stripe_payment,
                complaint=complaint,
                amount=order.total_amount,
                source=source,
                status='succeeded',
                stripe_refund_id=result,
                processed_by=actor,
                processed_at=timezone.now(),
                reason=f'Automatic Stripe refund — {source}',
            )

            log_audit(request, 'refund_issued', target=refund,
                      description=f'Stripe refund issued for Order #{order.id} (Stripe refund {result})',
                      metadata={'stripe_refund_id': result, 'amount': str(order.total_amount), 'source': source},
                      actor=actor)

            notify(order.customer,
                   title='Refund issued 💰',
                   message=f'A refund of RM {order.total_amount} for Order #{order.id} '
                           f'has been sent to your card. It may take 3–5 business days to appear.',
                   link=f'/order-details/{order.id}/',
                   notification_type='payment')
        else:
            # Stripe call failed — log and create manual record
            logger.error(f'Stripe refund failed for Order #{order.id}: {result}')
            refund = Refund.objects.create(
                order=order,
                payment=stripe_payment,
                complaint=complaint,
                amount=order.total_amount,
                source=source,
                status='failed',
                reason=f'Stripe auto-refund failed: {result}',
                processed_by=actor,
            )

            log_audit(request, 'refund_failed', target=refund,
                      description=f'Stripe refund FAILED for Order #{order.id}: {result}',
                      metadata={'error': result, 'amount': str(order.total_amount), 'source': source},
                      actor=actor)

            notify(order.customer,
                   title='Refund pending ⚠️',
                   message=f'We attempted to refund Order #{order.id} automatically but encountered '
                           f'an issue. Our team will process it manually within 1–2 business days.',
                   link=f'/order-details/{order.id}/',
                   notification_type='payment')
    else:
        # Manual payment (DuitNow / bank transfer) — flag for manager
        manual_payment = order.payments.filter(payment_method='manual').first()
        refund = Refund.objects.create(
            order=order,
            payment=manual_payment,
            complaint=complaint,
            amount=order.total_amount,
            source=source,
            status='manual',
            reason=f'Manual payment — manager must refund via bank transfer ({source})',
            processed_by=actor,
        )

        log_audit(request, 'refund_manual', target=refund,
                  description=f'Manual refund required for Order #{order.id} — RM {order.total_amount} via bank transfer',
                  metadata={'amount': str(order.total_amount), 'source': source},
                  actor=actor)

        notify(order.customer,
               title='Refund in progress 🏦',
               message=f'Your refund request for Order #{order.id} has been received. '
                       f'Our team will transfer RM {order.total_amount} to your account '
                       f'within 3–5 business days.',
               link=f'/order-details/{order.id}/',
               notification_type='payment')

    return refund


def remake_order(original_order, resolved_by, request=None):
    """
    Clone a completed order back into the approved queue as a priority remake.

    - Copies all items, delivery address, and customer from the original.
    - Status is set directly to 'approved' (skips pending queue entirely).
    - Generates and digitally signs a new receipt immediately.

    Returns the new Order instance.
    """
    from admins.models import Order, OrderItem, DigitalSignature
    from admins.utils import generate_invoice_pdf, sign_pdf_digitally, compute_order_integrity_hash
    from admins.notifications import log_audit, notify

    new_order = Order.objects.create(
        customer=original_order.customer,
        full_name=original_order.full_name,
        phone_number=original_order.phone_number,
        street_address=original_order.street_address,
        city=original_order.city,
        state=original_order.state,
        postcode=original_order.postcode,
        latitude=original_order.latitude,
        longitude=original_order.longitude,
        formatted_address=original_order.formatted_address,
        order_notes=f'[REMAKE of Order #{original_order.id}]'
                    + (f' — {original_order.order_notes}' if original_order.order_notes else ''),
        total_amount=original_order.total_amount,
        status='approved',
        approved_at=timezone.now(),
        approved_by=resolved_by,
        is_remake=True,
        remake_of=original_order,
        is_priority=True,
    )

    from customers.models import Product
    from django.db import transaction
    with transaction.atomic():
        # Lock products and decrement stock — remake consumes real inventory
        product_ids = [item.product_id for item in original_order.items.all()]
        locked = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)}
        for item in original_order.items.select_related('product').all():
            product = locked.get(item.product_id)
            if product and not product.is_unlimited_stock:
                if item.is_bundle:
                    if product.bundle_stock is not None:
                        if product.bundle_stock < item.quantity:
                            raise ValueError(
                                f"Cannot remake: bundle '{product.name}' only has "
                                f"{product.bundle_stock} unit(s) left."
                            )
                        product.bundle_stock -= item.quantity
                        product.save(update_fields=['bundle_stock'])
                else:
                    if product.stock < item.quantity:
                        raise ValueError(
                            f"Cannot remake: '{product.name}' only has "
                            f"{product.stock} unit(s) left."
                        )
                    product.stock -= item.quantity
                    product.save(update_fields=['stock'])
            OrderItem.objects.create(
                order=new_order,
                product=item.product,
                quantity=item.quantity,
                unit_price=item.unit_price,
                is_bundle=item.is_bundle,
                subtotal=item.subtotal,
            )

    # Sign a fresh receipt for the remake
    try:
        from django.utils import timezone as tz
        now = tz.now()
        order_hash = compute_order_integrity_hash(new_order)
        raw_pdf = generate_invoice_pdf(new_order, sig_hash=order_hash, sig_timestamp=now, approved_at=now)
        signed_path, file_hash, sig_value = sign_pdf_digitally(raw_pdf, new_order.id)
        DigitalSignature.objects.create(
            order=new_order,
            signature_hash=file_hash,
            pdf_path=os.path.join('signed_pdfs', os.path.basename(signed_path)),
            signature_value=sig_value,
        )
    except Exception as e:
        logger.warning(f'Could not sign receipt for remake order #{new_order.id}: {e}')

    log_audit(request, 'order_approved', target=new_order,
              description=f'Remake order #{new_order.id} created from Order #{original_order.id}',
              metadata={'original_order_id': original_order.id},
              actor=resolved_by)

    notify(original_order.customer,
           title='Your order is being remade 🍽️',
           message=f'Following your complaint on Order #{original_order.id}, we are remaking '
                   f'your order at no extra charge (New Order #{new_order.id}).',
           link=f'/order-details/{new_order.id}/',
           notification_type='order_update')

    return new_order
