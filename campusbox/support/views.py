from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, When
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
    return render(request, "support/my_tickets.html", {"tickets": tickets})


TICKET_FILTERS = [("", "All")] + SupportTicket.STATUS_CHOICES


def staff_tickets(request):
    """List support tickets for staff, with search and a status filter."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    tickets = SupportTicket.objects.select_related("user", "order").order_by(
        Case(
            When(status="open", then=0),
            default=1,
            output_field=IntegerField(),
        ),
        "-created_at",
    )
    if status in dict(SupportTicket.STATUS_CHOICES):
        tickets = tickets.filter(status=status)
    if q:
        # "12" or "#12" finds ticket 12 or order 12; any text also matches usernames
        number = q.lstrip("#")
        match = Q(user__username__icontains=q)
        if number.isdigit():
            match |= Q(id=number) | Q(order__id=number)
        tickets = tickets.filter(match)

    page_obj = Paginator(tickets, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)  # page links add their own page number
    return render(request, "support/staff_tickets.html", {
        "page_obj": page_obj,
        "querystring": params.urlencode(),
        "status": status,
        "q": q,
        "filters": TICKET_FILTERS,
    })


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
        return redirect("dashboard:tickets")
    return render(request, "support/staff_ticket_detail.html", {
        "ticket": ticket,
        "form": form,
    })
