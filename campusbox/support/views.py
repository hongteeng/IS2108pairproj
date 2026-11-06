from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, When
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Order

from .forms import StaffTicketForm, TicketForm
from .models import SupportTicket


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


def staff_tickets(request):
    """List support tickets for staff."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    tickets = SupportTicket.objects.select_related("user", "order").order_by(
        Case(
            When(status="open", then=0),
            default=1,
            output_field=IntegerField(),
        ),
        "-created_at",
    )
    return render(request, "support/staff_tickets.html", {"tickets": tickets})


def staff_ticket_detail(request, ticket_id):
    """Show and update a support ticket for staff."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    ticket = get_object_or_404(
        SupportTicket.objects.select_related("user", "order"),
        id=ticket_id,
    )
    form = StaffTicketForm(request.POST or None, instance=ticket)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ticket updated.")
        return redirect("support:staff_tickets")
    return render(request, "support/staff_ticket_detail.html", {
        "ticket": ticket,
        "form": form,
        "order_total_dollars": f"{ticket.order.total_cents / 100:.2f}",
    })
