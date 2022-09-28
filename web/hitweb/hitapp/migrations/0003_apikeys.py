# Generated by Django 3.2.15 on 2022-09-28 22:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hitapp', '0002_proxies_proxyusage'),
    ]

    operations = [
        migrations.CreateModel(
            name='APIKeys',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyname', models.CharField(max_length=40)),
                ('keyvalue', models.CharField(max_length=200)),
                ('keytag', models.CharField(max_length=20)),
                ('added', models.DateTimeField(auto_now=True)),
                ('edited', models.DateTimeField(auto_now_add=True)),
                ('deleted', models.DateTimeField(default=None, null=True)),
            ],
            options={
                'verbose_name': 'API Keys Table',
                'db_table': 'hitweb_apikeys',
            },
        ),
    ]