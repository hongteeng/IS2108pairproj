from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.utils.timezone import localtime
from accounts.forms import RegisterForm
from menu.models import Meal, WeeklyMenu, MenuItem
from orders.models import PickupPoint, PickupSlot
from .roles import ROLE_CHOICES, STAFF

class MealForm(forms.ModelForm):
    # Staff type dollars; the database still stores whole cents.
    price = forms.DecimalField(
        label='Price',
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
            'description': forms.Textarea(attrs={'rows': 3}),
            # btn-check turns each tick-box into a pill toggle, like the menu filters
            'dietary_tags': forms.CheckboxSelectMultiple(attrs={'class': 'btn-check'}),
            'allergens': forms.CheckboxSelectMultiple(attrs={'class': 'btn-check'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
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
        self.fields['category'].empty_label = 'Choose a category'
        self.fields['protein_g'].label = 'Protein'
        self.fields['carbs_g'].label = 'Carbs'
        self.fields['fat_g'].label = 'Fat'
        self.fields['is_active'].label = 'Show on the storefront'
        self.fields['is_active'].help_text = 'Untick to hide this meal from students without deleting it.'
        self.fields['image_url'].label = 'Image URL'
        self.fields['image_url'].help_text = 'A photo in menu/static/menu/meals/, e.g. /static/menu/meals/chicken-rice-box.jpg, or a full https:// link'

    def nutrition_fields(self):
        """The four nutrition fields with their units, for one row in the template."""
        return [(self['calories'], 'kcal'), (self['protein_g'], 'g'),
                (self['carbs_g'], 'g'), (self['fat_g'], 'g')]

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

    def clean(self):
        """A slot is on a weekday, not in the past, and ends after it starts."""
        cleaned_data = super().clean()
        day = cleaned_data.get('day')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if day:
            if day < timezone.localdate():
                self.add_error('day', 'Pick today or a later date.')
            elif day.weekday() > 4:
                self.add_error('day', 'Pickups run Monday to Friday, like the menu.')
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', 'The end time must be after the start time.')
        return cleaned_data


class StaffAccountForm(RegisterForm):
    """The sign-up fields plus a role. Only owners get the role field, so HR can only add plain staff."""

    role = forms.ChoiceField(choices=ROLE_CHOICES, initial=STAFF, required=False,
                             widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, can_choose_role=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_choose_role:
            del self.fields['role']
