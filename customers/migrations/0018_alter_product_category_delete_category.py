from django.db import migrations, models


def fix_category_column(apps, schema_editor):
    """
    Production has category_id (ForeignKey) and customers_category table.
    Local dev already has category (CharField) and no customers_category table.
    Normalise both to a plain VARCHAR category column.
    """
    db = schema_editor.connection
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='customers_product' AND column_name='category_id'"
        )
        has_fk = cursor.fetchone() is not None

        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='customers_product' AND column_name='category'"
        )
        has_plain = cursor.fetchone() is not None

        cursor.execute(
            "SELECT to_regclass('public.customers_category')"
        )
        category_table_exists = cursor.fetchone()[0] is not None

    if has_fk:
        schema_editor.execute("ALTER TABLE customers_product DROP COLUMN category_id")

    if not has_plain:
        schema_editor.execute(
            "ALTER TABLE customers_product ADD COLUMN category VARCHAR(100) NOT NULL DEFAULT ''"
        )

    if category_table_exists:
        schema_editor.execute("DROP TABLE customers_category")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0017_product_bundle_stock'),
    ]

    operations = [
        migrations.RunPython(fix_category_column, noop),
        # Bring Django's migration state in sync — SeparateDatabaseAndState so Django
        # knows the model is gone without trying to DROP TABLE again.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='Category'),
                migrations.AlterField(
                    model_name='product',
                    name='category',
                    field=models.CharField(blank=True, default='', max_length=100),
                ),
            ],
        ),
    ]
