from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import CustomerProfile


class RegisterForm(forms.Form):
    """Sign-up form with the password entered twice."""

    username = forms.CharField(max_length=50,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(min_length=8,
                               widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(label='Confirm password',
                                       widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_username(self):
        """Reject usernames that are already taken."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        """Reject email addresses that are already registered."""
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email
    
    def clean_password(self):
        """Apply the password rules from settings (too common, all numbers)."""
        password = self.cleaned_data['password']
        validate_password(password)
        return password


    def clean(self):
        """Check that both passwords match."""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if password and confirm and password != confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class LoginForm(forms.Form):
    """Username and password login form."""

    username = forms.CharField(max_length=50,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))


class TasteQuizForm(forms.ModelForm):
    """Collects customer preferences for meal recommendations."""

    class Meta:
        model = CustomerProfile
        fields = [
            "age",
            "gender",
            "is_on_campus",
            "budget_per_meal",
            "fitness_goal",
            "spice_tolerance",
            "diet",
            "allergies",
        ]
        labels = {
            "is_on_campus": "I live on campus",
            "budget_per_meal": "Budget per meal ($)",
            "spice_tolerance": "How spicy do you like it?",
        }
        widgets = {
            "age": forms.NumberInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "is_on_campus": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "budget_per_meal": forms.NumberInput(attrs={"class": "form-control"}),
            "fitness_goal": forms.Select(attrs={"class": "form-select"}),
            "spice_tolerance": forms.Select(attrs={"class": "form-select"}),
            "diet": forms.Select(attrs={"class": "form-select"}),
            "allergies": forms.CheckboxSelectMultiple(
                attrs={"class": "form-check-input"},
            ),
        }

    def clean_age(self):
        """Keep ages realistic for university students."""
        age = self.cleaned_data["age"]
        if not 16 <= age <= 60:
            raise forms.ValidationError("Age must be between 16 and 60.")
        return age

    def clean_budget_per_meal(self):
        """Keep budgets within a sensible range."""
        budget = self.cleaned_data["budget_per_meal"]
        if not 3 <= budget <= 30:
            raise forms.ValidationError(
                "Budget per meal must be between $3 and $30."
            )
        return budget