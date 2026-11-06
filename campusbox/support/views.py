from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Order

from .forms import TicketForm


@login_required
def report_problem(request, order_id):
    """Report a problem with a ready or collected order."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in {"ready", "collected"}:
        messages.error(request, "You can report a problem once your order is ready.")
        return redirect("orders:order_detail", order_id=order.id)

    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.user = request.user
        ticket.order = order
        ticket.save()
        messages.success(
            request,
            "Thanks, we’ve received your report. We’ll reply soon.",
        )
        return redirect("support:my_tickets")

    return render(request, "support/report_form.html", {
        "form": form,
        "order": order,
    })


@login_required
def my_tickets(request):
    """List the student's support tickets."""
    tickets = request.user.tickets.select_related("order")
    for ticket in tickets:
        ticket.refund_dollars = f"{ticket.refund_amount_cents / 100:.2f}"
    return render(request, "support/my_tickets.html", {"tickets": tickets})
