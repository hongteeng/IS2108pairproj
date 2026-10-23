from django import forms
from .models import User


class RegisterForm(forms.Form):
    """Sign-up form with the password entered twice."""
    
    username = forms.CharField(max_length=50,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
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

    def clean(self):
        """Check that both passwords match."""
        
        cleaned_data = super().clean()
        if cleaned_data.get('password') != cleaned_data.get('confirm_password'):
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class LoginForm(forms.Form):
    """Username and password login form."""
    
    username = forms.CharField(max_length=50,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))