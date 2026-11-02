from django import forms
from menu.models import Meal, WeeklyMenu, MenuItem

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