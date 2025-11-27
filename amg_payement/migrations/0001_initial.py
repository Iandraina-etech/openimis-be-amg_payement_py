from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('purchaseref', models.CharField(max_length=64, unique=True)),
                ('openimis_ref', models.CharField(max_length=64)),
                # ('beneficiary_id', models.CharField(max_length=64)),
                ('amount', models.IntegerField()),
                ('currency', models.IntegerField(default=174)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(default='initiated', max_length=32)),
                ('ref_trans', models.CharField(blank=True, max_length=128)),
                ('merchantid', models.CharField(blank=True, max_length=32)),
                ('sessionid', models.CharField(blank=True, max_length=128)),
                ('msisdn', models.CharField(blank=True, max_length=32)),
                ('timestamp', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]