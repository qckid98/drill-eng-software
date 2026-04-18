from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
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
    CoringIntervalFormSet,
    FormationMarkerFormSet,
    OperationalRateFormSet,
    ProposalGeneralForm,
    TubeLengthRangeFormSet,
    TubingSpecFormSet,
    WellForm,
    _make_activity_formset,
)
from .models import (
    CasingSection,
    CompletionSpec,
    Proposal,
    ProposalStatus,
    TubingItem,
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
    qs = (
        Proposal.objects
        .select_related("well", "created_by")
        .exclude(status=ProposalStatus.TEMPLATE)
    )

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

    # Available templates for "new from template" button
    templates = Proposal.objects.filter(status=ProposalStatus.TEMPLATE).select_related("well")

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "proposals/dashboard.html", {
        "proposals": page,
        "page_obj": page,
        "status_choices": [
            c for c in ProposalStatus.choices if c[0] != ProposalStatus.TEMPLATE
        ],
        "current_status": status,
        "q": q,
        "templates": templates,
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
# Create from template
# ---------------------------------------------------------------------------
@login_required
def proposal_create_from_template(request, template_pk):
    if not (request.user.is_engineer or request.user.is_admin_role):
        return HttpResponseForbidden("Hanya Drilling Engineer yang dapat membuat proposal.")

    template = get_object_or_404(Proposal, pk=template_pk, status=ProposalStatus.TEMPLATE)

    if request.method == "POST":
        well_form = WellForm(request.POST, prefix="well")
        if well_form.is_valid():
            well = well_form.save()
            proposal = template.clone_from_template(request.user, well)
            recalculate_proposal(proposal)
            messages.success(
                request,
                f"Proposal dibuat dari template '{template.title}'. "
                f"Silakan review dan edit sesuai kebutuhan."
            )
            return redirect("proposals:detail", pk=proposal.pk)
    else:
        # Pre-fill well form from template's well
        well_form = WellForm(prefix="well", initial={
            "name": "",
            "location": "",
            "cluster": template.well.cluster,
            "field": template.well.field,
            "basin": template.well.basin,
            "operator": template.well.operator,
            "contract_area": template.well.contract_area,
            "target_formation": template.well.target_formation,
            "project_type": template.well.project_type,
            "well_type": template.well.well_type,
            "well_category": template.well.well_category,
        })

    return render(request, "proposals/create_from_template.html", {
        "template": template,
        "well_form": well_form,
    })


# ---------------------------------------------------------------------------
# Detail (read-only view with chart + approval actions)
# ---------------------------------------------------------------------------
@login_required
def proposal_detail(request, pk):
    proposal = get_object_or_404(
        Proposal.objects.select_related("well", "rig", "created_by"), pk=pk,
    )
    # IDOR protection: engineers can only see their own proposals
    if request.user.is_engineer and proposal.created_by != request.user:
        return HttpResponseForbidden("Anda tidak memiliki akses ke proposal ini.")
    sections = proposal.casing_sections.prefetch_related("activities__activity").all()

    # Build chart series
    chart_labels = [str(s.hole_section.label) for s in sections]
    chart_drilling = [float(s.drilling_days) for s in sections]
    chart_non_drilling = [float(s.non_drilling_days) for s in sections]
    chart_completion = [float(s.completion_days) for s in sections]

    # Cumulative days for drilling curve
    cum_days = []
    cum_depth = []
    running_days = float(proposal.mob_days or 0)
    running_depth = 0
    for s in sections:
        cum_days.append(round(running_days, 2))
        cum_depth.append(round(float(s.previous_depth), 2))
        running_days += float(s.total_days)
        running_depth = float(s.depth_m)
        cum_days.append(round(running_days, 2))
        cum_depth.append(round(running_depth, 2))

    return render(request, "proposals/detail.html", {
        "proposal": proposal,
        "sections": sections,
        "chart_labels": chart_labels,
        "chart_drilling": chart_drilling,
        "chart_non_drilling": chart_non_drilling,
        "chart_completion": chart_completion,
        "cum_days": cum_days,
        "cum_depth": cum_depth,
        "approval_form": ApprovalActionForm(),
        "approval_logs": proposal.approval_logs.select_related("actor").all(),
        "can_edit": proposal.can_edit(request.user),
        "can_submit": proposal.can_submit(request.user),
        "can_review": proposal.can_review(request.user),
        "can_approve": proposal.can_approve(request.user),
        "tubing_specs": proposal.tubing_items.all(),
        "operational_rates": proposal.operational_rates.all(),
        "formation_markers": proposal.well.formation_markers.all(),
    })


# ---------------------------------------------------------------------------
# Edit -- general / casing / tubing / completion / rates / markers
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

    if request.method == "POST":
        tubing_fs = TubingSpecFormSet(request.POST, instance=proposal, prefix="tubing")
        marker_fs = FormationMarkerFormSet(request.POST, instance=proposal.well, prefix="marker")
        range_fs = TubeLengthRangeFormSet(request.POST, instance=proposal, prefix="range")
        if tubing_fs.is_valid() and marker_fs.is_valid() and range_fs.is_valid():
            tubing_fs.save()
            marker_fs.save()
            range_fs.save()
            messages.success(request, "Tubing, formation markers, dan tube length ranges disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        tubing_fs = TubingSpecFormSet(instance=proposal, prefix="tubing")
        marker_fs = FormationMarkerFormSet(instance=proposal.well, prefix="marker")
        range_fs = TubeLengthRangeFormSet(instance=proposal, prefix="range")

    return render(request, "proposals/edit_tubing.html", {
        "proposal": proposal,
        "tubing_formset": tubing_fs,
        "marker_formset": marker_fs,
        "range_formset": range_fs,
    })


@login_required
def proposal_edit_completion(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    comp_spec, _ = CompletionSpec.objects.get_or_create(proposal=proposal)
    if request.method == "POST":
        form = CompletionSpecForm(request.POST, instance=comp_spec)
        coring_fs = CoringIntervalFormSet(request.POST, instance=comp_spec, prefix="coring")
        if form.is_valid() and coring_fs.is_valid():
            form.save()
            coring_fs.save()
            messages.success(request, "Completion spec dan coring intervals disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        form = CompletionSpecForm(instance=comp_spec)
        coring_fs = CoringIntervalFormSet(instance=comp_spec, prefix="coring")

    return render(request, "proposals/edit_completion.html", {
        "proposal": proposal,
        "form": form,
        "coring_formset": coring_fs,
    })


@login_required
def proposal_edit_rates(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    if request.method == "POST":
        formset = OperationalRateFormSet(request.POST, instance=proposal)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Operational rates disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        formset = OperationalRateFormSet(instance=proposal)

    return render(request, "proposals/edit_simple.html", {
        "proposal": proposal, "formset": formset,
        "section_title": "Operational Rates",
    })


@login_required
def proposal_edit_markers(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    if request.method == "POST":
        formset = FormationMarkerFormSet(request.POST, instance=proposal.well)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Formation markers disimpan.")
            return redirect("proposals:detail", pk=pk)
    else:
        formset = FormationMarkerFormSet(instance=proposal.well)

    return render(request, "proposals/edit_simple.html", {
        "proposal": proposal, "formset": formset,
        "section_title": "Formation Markers",
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

    # Build formset with activities filtered by this section's hole size
    ActivityFormSet = _make_activity_formset(hole_section=section.hole_section)

    if request.method == "POST":
        formset = ActivityFormSet(request.POST, instance=section)
        if formset.is_valid():
            formset.save()
            recalculate_proposal(proposal)
            messages.success(request, f"Aktivitas untuk section {section.hole_section} disimpan.")
            return redirect("proposals:casing_activities", pk=pk, section_id=section_id)
    else:
        formset = ActivityFormSet(instance=section)

    from masterdata.models import SectionTemplate
    available_templates = SectionTemplate.objects.filter(
        Q(hole_section=section.hole_section) | Q(hole_section__isnull=True)
    ).order_by("order")

    return render(request, "proposals/edit_activities.html", {
        "proposal": proposal,
        "section": section,
        "formset": formset,
        "category_l1": ActivityCategoryL1.objects.all(),
        "section_templates": available_templates,
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
    hs_id = request.GET.get("hole_section")
    qs = DrillingActivity.objects.filter(category_l2_id=l2_id) if l2_id else DrillingActivity.objects.none()
    # Filter by hole section if provided
    if hs_id:
        qs = qs.filter(
            Q(applies_to_hole_sections__isnull=True)
            | Q(applies_to_hole_sections__id=hs_id)
        ).distinct()
    return render(request, "proposals/partials/options_activity.html", {"items": qs})


@login_required
@require_http_methods(["POST"])
def apply_section_template(request, pk, section_id):
    """Apply a SectionTemplate to a casing section's activities."""
    from masterdata.models import SectionTemplate
    from .services.templates import apply_template_to_section

    proposal = get_object_or_404(Proposal, pk=pk)
    section = get_object_or_404(CasingSection, pk=section_id, proposal=proposal)
    try:
        _require_edit(request.user, proposal)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    template_id = request.POST.get("template_id")
    if not template_id:
        messages.error(request, "Pilih template terlebih dahulu.")
        return redirect("proposals:casing_activities", pk=pk, section_id=section_id)

    try:
        template = SectionTemplate.objects.get(pk=template_id)
    except SectionTemplate.DoesNotExist:
        messages.error(request, "Template tidak ditemukan.")
        return redirect("proposals:casing_activities", pk=pk, section_id=section_id)

    replace = request.POST.get("replace") == "1"
    apply_template_to_section(section, template, replace=replace)
    messages.success(
        request,
        f"Template '{template.name}' diterapkan ke section {section.hole_section}."
        f"{' (aktivitas lama dihapus)' if replace else ''}"
    )
    return redirect("proposals:casing_activities", pk=pk, section_id=section_id)
