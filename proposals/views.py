from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from masterdata.models import ActivityCategoryL1, ActivityCategoryL2, DrillingActivity

from .forms import (
    ApprovalActionForm,
    CasingSectionFormSet,
    CompletionSpecForm,
    ProposalActivityFormSet,
    ProposalGeneralForm,
    TubingSpecForm,
    WellForm,
)
from .models import (
    CasingSection,
    CompletionSpec,
    Proposal,
    ProposalStatus,
    TubingSpec,
)
from .services import approval
from .services.calc import recalculate_proposal


# ---------------------------------------------------------------------------
# List / dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    status = request.GET.get("status") or ""
    q = request.GET.get("q") or ""
    qs = Proposal.objects.select_related("well", "created_by").all()

    # Engineers only see their own proposals; supervisors/management see all
    if request.user.is_engineer:
        qs = qs.filter(created_by=request.user)

    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(doc_number__icontains=q)
            | Q(well__name__icontains=q)
            | Q(well__location__icontains=q)
        )

    return render(request, "proposals/dashboard.html", {
        "proposals": qs[:200],
        "status_choices": ProposalStatus.choices,
        "current_status": status,
        "q": q,
    })


@login_required
def inbox(request):
    user = request.user
    qs = Proposal.objects.select_related("well", "created_by")
    if user.is_supervisor:
        qs = qs.filter(status=ProposalStatus.SUBMITTED)
    elif user.is_management:
        qs = qs.filter(status=ProposalStatus.UNDER_REVIEW)
    elif user.is_engineer:
        qs = qs.filter(created_by=user, status=ProposalStatus.REVISION)
    else:
        qs = qs.none()
    return render(request, "proposals/inbox.html", {"proposals": qs})


# ---------------------------------------------------------------------------
# Create (Step 1: well + proposal general data in one form)
# ---------------------------------------------------------------------------
@login_required
def proposal_create(request):
    if not (request.user.is_engineer or request.user.is_admin_role):
        return HttpResponseForbidden("Hanya Drilling Engineer yang dapat membuat proposal.")

    if request.method == "POST":
        well_form = WellForm(request.POST, prefix="well")
        prop_form = ProposalGeneralForm(request.POST, prefix="prop")
        if well_form.is_valid() and prop_form.is_valid():
            well = well_form.save()
            proposal = prop_form.save(commit=False)
            proposal.well = well
            proposal.created_by = request.user
            proposal.save()
            messages.success(request, "Proposal draft dibuat. Lanjutkan isi casing design.")
            return redirect("proposals:edit_casing", pk=proposal.pk)
    else:
        well_form = WellForm(prefix="well")
        prop_form = ProposalGeneralForm(prefix="prop")

    return render(request, "proposals/create.html", {
        "well_form": well_form, "prop_form": prop_form,
    })


# ---------------------------------------------------------------------------
# Detail (read-only view with chart + approval actions)
# ---------------------------------------------------------------------------
@login_required
def proposal_detail(request, pk):
    proposal = get_object_or_404(
        Proposal.objects.select_related("well", "rig", "created_by"), pk=pk,
    )
    sections = proposal.casing_sections.prefetch_related("activities__activity").all()

    # Build chart series
    chart_labels = [str(s.hole_section.label) for s in sections]
    chart_drilling = [float(s.drilling_days) for s in sections]
    chart_non_drilling = [float(s.non_drilling_days) for s in sections]

    return render(request, "proposals/detail.html", {
        "proposal": proposal,
        "sections": sections,
        "chart_labels": chart_labels,
        "chart_drilling": chart_drilling,
        "chart_non_drilling": chart_non_drilling,
        "approval_form": ApprovalActionForm(),
        "approval_logs": proposal.approval_logs.select_related("actor").all(),
        "can_edit": proposal.can_edit(request.user),
        "can_submit": proposal.can_submit(request.user),
        "can_review": proposal.can_review(request.user),
        "can_approve": proposal.can_approve(request.user),
    })


# ---------------------------------------------------------------------------
# Edit — general / casing / tubing / completion
# ---------------------------------------------------------------------------
def _require_edit(user, proposal):
    if not proposal.can_edit(user):
        raise PermissionError("Proposal tidak dapat diedit pada status saat ini.")


@login_required
def proposal_edit_general(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    if request.method == "POST":
        well_form = WellForm(request.POST, prefix="well", instance=proposal.well)
        prop_form = ProposalGeneralForm(request.POST, prefix="prop", instance=proposal)
        if well_form.is_valid() and prop_form.is_valid():
            well_form.save()
            prop_form.save()
            messages.success(request, "Data umum diperbarui.")
            return redirect("proposals:detail", pk=pk)
    else:
        well_form = WellForm(prefix="well", instance=proposal.well)
        prop_form = ProposalGeneralForm(prefix="prop", instance=proposal)

    return render(request, "proposals/edit_general.html", {
        "proposal": proposal, "well_form": well_form, "prop_form": prop_form,
    })


@login_required
def proposal_edit_casing(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    if request.method == "POST":
        formset = CasingSectionFormSet(request.POST, instance=proposal)
        if formset.is_valid():
            formset.save()
            recalculate_proposal(proposal)
            messages.success(request, "Casing design disimpan.")
            if "save_and_continue" in request.POST:
                return redirect("proposals:edit_casing", pk=pk)
            return redirect("proposals:detail", pk=pk)
    else:
        formset = CasingSectionFormSet(instance=proposal)

    return render(request, "proposals/edit_casing.html", {
        "proposal": proposal, "formset": formset,
    })


@login_required
def proposal_edit_tubing(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    instance, _ = TubingSpec.objects.get_or_create(proposal=proposal)
    if request.method == "POST":
        form = TubingSpecForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Tubing spec disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        form = TubingSpecForm(instance=instance)
    return render(request, "proposals/edit_simple.html", {
        "proposal": proposal, "form": form, "section_title": "Tubing Specification",
    })


@login_required
def proposal_edit_completion(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    instance, _ = CompletionSpec.objects.get_or_create(proposal=proposal)
    if request.method == "POST":
        form = CompletionSpecForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Completion spec disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        form = CompletionSpecForm(instance=instance)
    return render(request, "proposals/edit_simple.html", {
        "proposal": proposal, "form": form, "section_title": "Completion Specification",
    })


# ---------------------------------------------------------------------------
# Activities per casing section (the bulk of the wizard)
# ---------------------------------------------------------------------------
@login_required
def casing_activities(request, pk, section_id):
    proposal = get_object_or_404(Proposal, pk=pk)
    section = get_object_or_404(CasingSection, pk=section_id, proposal=proposal)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    if request.method == "POST":
        formset = ProposalActivityFormSet(request.POST, instance=section)
        if formset.is_valid():
            formset.save()
            recalculate_proposal(proposal)
            messages.success(request, f"Aktivitas untuk section {section.hole_section} disimpan.")
            return redirect("proposals:casing_activities", pk=pk, section_id=section_id)
    else:
        formset = ProposalActivityFormSet(instance=section)

    return render(request, "proposals/edit_activities.html", {
        "proposal": proposal,
        "section": section,
        "formset": formset,
        "category_l1": ActivityCategoryL1.objects.all(),
    })


# ---------------------------------------------------------------------------
# Approval action
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["POST"])
def proposal_action(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    action = request.POST.get("action")
    comment = request.POST.get("comment", "").strip()

    try:
        if action == "submit":
            approval.submit(proposal, request.user, comment)
            messages.success(request, "Proposal disubmit ke supervisor.")
        elif action == "forward":
            approval.forward(proposal, request.user, comment)
            messages.success(request, "Proposal diteruskan ke management.")
        elif action == "request_revision":
            approval.request_revision(proposal, request.user, comment)
            messages.info(request, "Revisi diminta ke engineer.")
        elif action == "approve":
            approval.approve(proposal, request.user, comment)
            messages.success(request, "Proposal disetujui.")
        elif action == "reject":
            approval.reject(proposal, request.user, comment)
            messages.warning(request, "Proposal ditolak.")
        else:
            messages.error(request, "Aksi tidak dikenal.")
    except approval.ApprovalError as exc:
        messages.error(request, str(exc))

    return redirect("proposals:detail", pk=pk)


# ---------------------------------------------------------------------------
# HTMX: cascading dropdown endpoints
# ---------------------------------------------------------------------------
@login_required
def api_l2_options(request):
    l1_id = request.GET.get("l1")
    qs = ActivityCategoryL2.objects.filter(parent_id=l1_id) if l1_id else ActivityCategoryL2.objects.none()
    return render(request, "proposals/partials/options_l2.html", {"items": qs})


@login_required
def api_activity_options(request):
    l2_id = request.GET.get("l2")
    qs = DrillingActivity.objects.filter(category_l2_id=l2_id) if l2_id else DrillingActivity.objects.none()
    return render(request, "proposals/partials/options_activity.html", {"items": qs})
