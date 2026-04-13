from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from proposals.models import Proposal, ProposalStatus

from .forms import AFEApprovalActionForm, AFEHeaderForm, AFELineFormSet
from .models import AFE, AFECategory, AFEStatus, AFETemplate
from .services import approval
from .services.calc import generate_afe_from_proposal, recalculate_afe


# ---------------------------------------------------------------------------
# Dashboard & Inbox
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    status = request.GET.get("status") or ""
    q = request.GET.get("q") or ""
    qs = AFE.objects.select_related("proposal", "proposal__well", "created_by").all()

    if request.user.is_engineer:
        qs = qs.filter(created_by=request.user)

    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(doc_number__icontains=q)
            | Q(proposal__well__name__icontains=q)
            | Q(title__icontains=q)
        )

    return render(request, "afe/dashboard.html", {
        "afes": qs[:200],
        "status_choices": AFEStatus.choices,
        "current_status": status,
        "q": q,
    })


@login_required
def inbox(request):
    user = request.user
    qs = AFE.objects.select_related("proposal", "proposal__well", "created_by")
    if user.is_supervisor:
        qs = qs.filter(status=AFEStatus.SUBMITTED)
    elif user.is_management:
        qs = qs.filter(status=AFEStatus.UNDER_REVIEW)
    elif user.is_engineer:
        qs = qs.filter(created_by=user, status=AFEStatus.REVISION)
    else:
        qs = qs.none()
    return render(request, "afe/inbox.html", {"afes": qs})


# ---------------------------------------------------------------------------
# Create from approved proposal
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["POST", "GET"])
def afe_create(request, proposal_pk):
    proposal = get_object_or_404(Proposal, pk=proposal_pk)
    user = request.user
    if not (user.is_engineer or user.is_admin_role):
        return HttpResponseForbidden("Hanya Drilling Engineer yang dapat membuat AFE.")
    if proposal.status != ProposalStatus.APPROVED:
        messages.error(request, "AFE hanya bisa dibuat dari Proposal yang sudah APPROVED.")
        return redirect("proposals:detail", pk=proposal.pk)

    prev = AFE.objects.filter(proposal=proposal).order_by("-version").first()
    version = (prev.version + 1) if prev else 1

    afe = AFE.objects.create(
        proposal=proposal,
        version=version,
        created_by=user,
        title=f"AFE {proposal.well.name} v{version}",
    )
    generate_afe_from_proposal(afe)
    messages.success(request, f"AFE v{version} dibuat. Silakan review & edit.")
    return redirect("afe:edit", pk=afe.pk)


# ---------------------------------------------------------------------------
# Detail / edit
# ---------------------------------------------------------------------------
def _group_lines(afe: AFE):
    """Return list of lines with derived display attrs grouped by section."""
    lines = (afe.lines
             .select_related("template", "rate_card_item")
             .order_by("template__order", "template__line_code"))
    groups = {}
    for line in lines:
        groups.setdefault(line.template.section, []).append(line)
    return groups


@login_required
def afe_detail(request, pk):
    afe = get_object_or_404(
        AFE.objects.select_related("proposal", "proposal__well", "created_by"),
        pk=pk,
    )
    lines = (afe.lines
             .select_related("template", "rate_card_item")
             .order_by("template__order", "template__line_code"))

    # Donut chart: breakdown by section (non-subtotal lines only)
    section_totals: dict[str, float] = {}
    for line in lines:
        if line.template.is_subtotal_row:
            continue
        key = line.template.get_section_display()
        section_totals[key] = section_totals.get(key, 0.0) + float(line.final_usd)

    chart_labels = list(section_totals.keys())
    chart_values = [round(v, 2) for v in section_totals.values()]

    return render(request, "afe/detail.html", {
        "afe": afe,
        "lines": lines,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "approval_form": AFEApprovalActionForm(),
        "approval_logs": afe.approval_logs.select_related("actor").all(),
        "can_edit": afe.can_edit(request.user),
        "can_submit": afe.can_submit(request.user),
        "can_review": afe.can_review(request.user),
        "can_approve": afe.can_approve(request.user),
    })


@login_required
def afe_edit(request, pk):
    afe = get_object_or_404(AFE, pk=pk)
    if not afe.can_edit(request.user):
        return HttpResponseForbidden("AFE tidak dapat diedit pada status saat ini.")

    if request.method == "POST":
        header_form = AFEHeaderForm(request.POST, instance=afe)
        formset = AFELineFormSet(request.POST, instance=afe)
        if header_form.is_valid() and formset.is_valid():
            header_form.save()
            formset.save()
            recalculate_afe(afe)
            messages.success(request, "AFE tersimpan.")
            if "save_and_continue" in request.POST:
                return redirect("afe:edit", pk=pk)
            return redirect("afe:detail", pk=pk)
    else:
        header_form = AFEHeaderForm(instance=afe)
        formset = AFELineFormSet(instance=afe)

    # Pair each form with its underlying line for the template (need template meta)
    lines_by_id = {l.id: l for l in afe.lines.select_related("template")}
    rows = []
    for form in formset.forms:
        line = lines_by_id.get(form.instance.pk)
        rows.append((form, line))

    return render(request, "afe/edit.html", {
        "afe": afe,
        "header_form": header_form,
        "formset": formset,
        "rows": rows,
    })


@login_required
@require_http_methods(["POST"])
def afe_regenerate(request, pk):
    afe = get_object_or_404(AFE, pk=pk)
    if not afe.can_edit(request.user):
        return HttpResponseForbidden("AFE tidak dapat diubah.")
    generate_afe_from_proposal(afe, overwrite=True)
    messages.success(request, "AFE di-regenerate dari rate card (override dihapus).")
    return redirect("afe:edit", pk=pk)


@login_required
@require_http_methods(["POST"])
def afe_action(request, pk):
    afe = get_object_or_404(AFE, pk=pk)
    action = request.POST.get("action")
    comment = request.POST.get("comment", "").strip()

    try:
        if action == "submit":
            approval.submit(afe, request.user, comment)
            messages.success(request, "AFE disubmit ke supervisor.")
        elif action == "forward":
            approval.forward(afe, request.user, comment)
            messages.success(request, "AFE diteruskan ke management.")
        elif action == "request_revision":
            approval.request_revision(afe, request.user, comment)
            messages.info(request, "Revisi diminta.")
        elif action == "approve":
            approval.approve(afe, request.user, comment)
            messages.success(request, "AFE disetujui.")
        elif action == "reject":
            approval.reject(afe, request.user, comment)
            messages.warning(request, "AFE ditolak.")
        else:
            messages.error(request, "Aksi tidak dikenal.")
    except approval.ApprovalError as exc:
        messages.error(request, str(exc))

    return redirect("afe:detail", pk=pk)
