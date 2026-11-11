from decimal import Decimal

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

    refund_dollars = forms.DecimalField(
        label="Refund ($)",
        max_digits=7,
        decimal_places=2,
        min_value=0,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["refund_dollars"].initial = (
            Decimal(self.instance.refund_amount_cents) / Decimal("100")
        )

    class Meta:
        model = SupportTicket
        fields = ["status", "refund_dollars", "staff_reply"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "staff_reply": forms.Textarea(attrs={"class": "form-control"}),
        }

    def clean_refund_dollars(self):
        """Validate the refund against the order total."""
        refund_dollars = self.cleaned_data["refund_dollars"] or Decimal("0")
        order_total_dollars = Decimal(self.instance.order.total_cents) / Decimal("100")
        if refund_dollars > order_total_dollars:
            raise forms.ValidationError(
                f"Refund can’t be more than the order total "
                f"(${order_total_dollars:.2f})."
            )
        return refund_dollars
    
    def clean(self):
        """Only resolved tickets can have a refund."""
        cleaned_data = super().clean()
        refund = cleaned_data.get("refund_dollars") or Decimal("0")
        if refund > 0 and cleaned_data.get("status") != "resolved":
            self.add_error("refund_dollars", "Set the status to Resolved to give a refund.")
        return cleaned_data

    def save(self, commit=True):
        """Save the ticket with the refund converted to cents."""
        refund_dollars = self.cleaned_data.get("refund_dollars") or Decimal("0")
        self.instance.refund_amount_cents = int(round(refund_dollars * 100))
        return super().save(commit=commit)
