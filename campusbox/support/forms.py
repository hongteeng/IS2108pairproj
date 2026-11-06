from django import forms

from .models import SupportTicket


class TicketForm(forms.ModelForm):
    """Form for submitting a support ticket."""

    class Meta:
        model = SupportTicket
        fields = ["issue_type", "message"]
        widgets = {
            "issue_type": forms.Select(attrs={"class": "form-select"}),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }


class StaffTicketForm(forms.ModelForm):
    """Form for staff to resolve a support ticket."""

    class Meta:
        model = SupportTicket
        fields = ["status", "refund_amount_cents", "staff_reply"]
        labels = {
            "refund_amount_cents": "Refund (cents)",
        }
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "refund_amount_cents": forms.NumberInput(
                attrs={"class": "form-control"}
            ),
            "staff_reply": forms.Textarea(attrs={"class": "form-control"}),
        }

    def clean_refund_amount_cents(self):
        """Validate the refund against the order total."""
        refund_amount_cents = self.cleaned_data["refund_amount_cents"]
        if refund_amount_cents < 0:
            raise forms.ValidationError("Refund cannot be negative.")
        if refund_amount_cents > self.instance.order.total_cents:
            raise forms.ValidationError(
                "Refund cannot exceed the order total."
            )
        return refund_amount_cents
