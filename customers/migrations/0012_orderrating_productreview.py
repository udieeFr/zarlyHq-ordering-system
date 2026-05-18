from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0025_support_message_immutable'),
        ('customers', '0011_db_indexes_and_perf'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField()),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rating', to='admins.order')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_ratings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['customer', '-created_at'], name='customers_orderrating_customer_idx')],
            },
        ),
        migrations.CreateModel(
            name='ProductReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField()),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='customers.product')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_reviews', to=settings.AUTH_USER_MODEL)),
                ('order', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product_reviews', to='admins.order')),
            ],
            options={
                'unique_together': {('product', 'customer', 'order')},
                'indexes': [models.Index(fields=['product', '-created_at'], name='customers_productreview_product_idx')],
            },
        ),
    ]
