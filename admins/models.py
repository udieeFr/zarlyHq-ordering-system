from django.db import models
from customers.models import User, Product

class Order(models.Model):
    # Matches Table 4.5.3: Status choices
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('pending_payment', 'Approved but pending payment'), # Added per PDF [cite: 351]
    )
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'customer'})
    
    # RENAMED: 'total_price' -> 'total_amount' to match PDF Table 4.5.3 [cite: 351]
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    # ADDED: Essential for the "Internal User Process Flow" (Figure 4.4.2) [cite: 225]
    payment_proof = models.ImageField(upload_to='payment_proofs/', null=True, blank=True)
    
    # Helper fields (Logic support - kept from your original code)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})

    def __str__(self):
        return f"Order #{self.id} - {self.customer} ({self.status})"

class OrderItem(models.Model):
    # Matches Table 4.5.4 [cite: 353]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.product.price * self.quantity
        super().save(*args, **kwargs)

class DigitalSignature(models.Model):
    # RENAMED: From 'SignedDocument' to 'DigitalSignature' (Table 4.5.5) [cite: 385]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='digital_signature')
    
    # RENAMED: 'document_hash' -> 'signature_hash' [cite: 387]
    signature_hash = models.CharField(max_length=64)  
    
    # RENAMED: 'signed_pdf' -> 'pdf_path' [cite: 390]
    pdf_path = models.FileField(upload_to='signed_pdfs/') 
    
    # RENAMED: 'signed_at' -> 'timestamp' [cite: 394]
    timestamp = models.DateTimeField(auto_now_add=True)

    # Helper field (Good to keep for debug, even if not in PDF)
    signature_value = models.TextField()

