import django.core.validators
from django.db import migrations, models

import menu.models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0002_menuitem_menuitem_sold_within_available'),
    ]

    operations = [
        migrations.AddField(
            model_name='meal',
            name='photo',
            field=models.ImageField(blank=True, upload_to=menu.models.meal_photo_path, validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])]),
        ),
        migrations.AlterField(
            model_name='meal',
            name='image_url',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
