from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import get_default_password_validators

from .models import CustomerProfile

RULES_BROKEN = "Your password doesn't follow the rules marked ✗."


def check_password_rules(password, user):
    """Each password rule from settings, with whether the password passed it (None if no password was typed)."""
    rules = []
    for validator in get_default_password_validators():
        passed = None
        if password:
            try:
                validator.validate(password, user)
                passed = True
            except forms.ValidationError:
                passed = False
        rules.append({'text': validator.get_help_text(), 'passed': passed})
    return rules


class RegisterForm(forms.Form):
    """Sign-up form with the password entered twice."""

    username = forms.CharField(max_length=50,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))  # rules come from password_rules()
    confirm_password = forms.CharField(label='Confirm password',
                                       widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_username(self):
        """Reject usernames that are already taken."""
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        """Reject email addresses that are already registered."""
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def password_rules(self):
        """The password rules for the template, marked passed or broken once the form has been sent."""
        data = self.data if self.is_bound else {}
        # An unsaved User lets the rules compare the password with the username and email
        user = User(username=data.get('username', ''), email=data.get('email', ''))
        return check_password_rules(data.get('password'), user)

    def clean(self):
        """Check the password rules from settings, then check that both passwords match."""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if password and any(rule['passed'] is False for rule in self.password_rules()):
            self.add_error('password', RULES_BROKEN)  # the ✗ next to each rule says which one
        if password and confirm and password != confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class ChangePasswordForm(PasswordChangeForm):
    """Django's change password form, with the rules marked the same way as on Sign up."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'  # same Bootstrap look as the other forms

    def password_rules(self):
        """The password rules for the template, marked passed or broken once the form has been sent."""
        return check_password_rules(self.data.get('new_password1') if self.is_bound else None, self.user)

    def clean(self):
        """Show one message on the new password instead of Django's rule messages on the confirmation."""
        cleaned_data = super().clean()
        if self.data.get('new_password1') and any(rule['passed'] is False for rule in self.password_rules()):
            self.add_error('new_password1', RULES_BROKEN)
            # Django puts the rule messages on new_password2; keep it only for a mismatch or an empty box
            if not (self.has_error('new_password2', 'password_mismatch') or self.has_error('new_password2', 'required')):
                self.errors.pop('new_password2', None)
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