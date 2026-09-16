import random
from django.db import migrations, models


def generate_billing_ref():
    allowed_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    return 'BL-' + ''.join(random.choices(allowed_chars, k=6))


def populate_billing_references(apps, schema_editor):
    """Backfill billing_reference for all existing Billing rows."""
    Billing = apps.get_model('transactions', 'Billing')
    for billing in Billing.objects.filter(billing_reference__isnull=True):
        ref = generate_billing_ref()
        while Billing.objects.filter(billing_reference=ref).exists():
            ref = generate_billing_ref()
        billing.billing_reference = ref
        billing.save()


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0035_alter_billing_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='billing_reference',
            field=models.CharField(
                blank=True, db_index=True, editable=False,
                max_length=12, null=True, unique=True,
            ),
        ),
        migrations.RunPython(populate_billing_references, migrations.RunPython.noop),
    ]
