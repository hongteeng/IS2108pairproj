from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    """Form for submitting a meal review."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].choices = Review.RATING_CHOICES

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(attrs={"class": "form-select"}),
            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "What did you think?",
                }
            ),
        }
