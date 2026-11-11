from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator
from django.utils.timezone import localtime
from menu.models import Meal, WeeklyMenu, MenuItem
from orders.models import PickupPoint, PickupSlot

class MealForm(forms.ModelForm):
    # Staff type dollars; the database still stores whole cents.
    price = forms.DecimalField(
        label='Price ($)',
        min_value=Decimal('0.01'),
        max_digits=6,
        decimal_places=2,
        help_text='e.g. 6.50',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
    )

    class Meta:
        model = Meal
        fields = ['name', 'description', 'price', 'calories', 'protein_g',
                  'carbs_g', 'fat_g', 'image_url', 'category', 'dietary_tags',
                  'allergens', 'is_active']
        widgets = {
            'dietary_tags': forms.CheckboxSelectMultiple,
            'allergens': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Editing: show the saved price in dollars, e.g. 650 -> 6.50
            self.initial['price'] = f"{self.instance.price_cents / 100:.2f}"
        for name in ['name', 'description', 'calories', 'protein_g',
                     'carbs_g', 'fat_g', 'image_url']:
            self.fields[name].widget.attrs['class'] = 'form-control'
        for name in ['calories', 'protein_g', 'carbs_g', 'fat_g']:
            self.fields[name].validators.append(MinValueValidator(0))
            self.fields[name].widget.attrs['min'] = 0
        self.fields['category'].widget.attrs['class'] = 'form-select'
        self.fields['protein_g'].label = 'Protein (g)'
        self.fields['carbs_g'].label = 'Carbs (g)'
        self.fields['fat_g'].label = 'Fat (g)'
        self.fields['image_url'].label = 'Image URL'
        self.fields['image_url'].help_text = 'A photo in menu/static/menu/meals/, e.g. /static/menu/meals/chicken-rice-box.jpg, or a full https:// link'

    def save(self, commit=True):
        # Convert dollars back to cents before saving, e.g. 6.50 -> 650
        self.instance.price_cents = int(self.cleaned_data['price'] * 100)
        return super().save(commit)


class WeeklyMenuForm(forms.ModelForm):
    class Meta:
        model = WeeklyMenu
        fields = ['week_start', 'order_cutoff']
        widgets = {
            'week_start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'order_cutoff': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }
    
    def clean(self):
        """A menu runs Monday to Friday, closes before it starts, and only one per week."""
        cleaned_data = super().clean()
        week_start = cleaned_data.get('week_start')
        order_cutoff = cleaned_data.get('order_cutoff')
        if week_start:
            if week_start.weekday() != 0:
                self.add_error('week_start', 'Pick a Monday.')
            elif WeeklyMenu.objects.filter(week_start=week_start).exclude(pk=self.instance.pk).exists():
                self.add_error('week_start', 'There is already a menu for this week.')
        if week_start and order_cutoff and localtime(order_cutoff).date() >= week_start:
            self.add_error('order_cutoff', 'The cutoff must be before the week starts.')
        return cleaned_data


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['meal', 'quantity_available']
        widgets = {
            'meal': forms.Select(attrs={'class': 'form-select'}),
            'quantity_available': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['meal'].queryset = Meal.objects.filter(is_active=True).order_by('name')  # only meals students can buy
        self.fields['quantity_available'].validators.append(MinValueValidator(0))
        self.fields['quantity_available'].widget.attrs['min'] = 0

class PickupPointForm(forms.ModelForm):
    class Meta:
        model = PickupPoint
        fields = ['name', 'location', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
        }


class PickupSlotForm(forms.ModelForm):
    class Meta:
        model = PickupSlot
        fields = ['day', 'start_time', 'end_time', 'capacity']
        widgets = {
            'day': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['capacity'].validators.append(MinValueValidator(1))
        self.fields['capacity'].widget.attrs['min'] = 1