from django import forms
from django.core.validators import MinValueValidator
from menu.models import Meal, WeeklyMenu, MenuItem
from orders.models import PickupPoint, PickupSlot

class MealForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ['name', 'description', 'price_cents', 'calories', 'protein_g',
                  'carbs_g', 'fat_g', 'image_url', 'category', 'dietary_tags',
                  'allergens', 'is_active']
        widgets = {
            'dietary_tags': forms.CheckboxSelectMultiple,
            'allergens': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ['name', 'description', 'price_cents', 'calories', 'protein_g',
                     'carbs_g', 'fat_g', 'image_url']:
            self.fields[name].widget.attrs['class'] = 'form-control'
        for name, minimum in {
            'price_cents': 1,
            'calories': 0,
            'protein_g': 0,
            'carbs_g': 0,
            'fat_g': 0,
        }.items():
            self.fields[name].validators.append(MinValueValidator(minimum))
            self.fields[name].widget.attrs['min'] = minimum
        self.fields['price_cents'].label = 'Price (cents)'
        self.fields['price_cents'].help_text = 'e.g. 650 = $6.50'
        self.fields['category'].widget.attrs['class'] = 'form-select'

class WeeklyMenuForm(forms.ModelForm):
    class Meta:
        model = WeeklyMenu
        fields = ['week_start', 'order_cutoff']
        widgets = {
            'week_start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'order_cutoff': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }


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