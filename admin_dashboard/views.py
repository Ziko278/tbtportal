import traceback
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin, messages
# from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
# from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from communication.models import RecentActivityModel
from finance.models import FeePaymentModel, FeeModel
from result.models import ResultModel, TextResultModel
from student.models import StudentsModel
from school_setting.models import SchoolGeneralInfoModel, SchoolAcademicInfoModel
from academic.models import ClassSectionInfoModel, ClassesModel, ClassSectionModel
from user_management.models import UserProfileModel


def setup_test():
    info = SchoolGeneralInfoModel.objects.first()
    if info:
        return True
    return False


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'admin_dashboard/dashboard.html'

    def dispatch(self, *args, **kwargs):
        if setup_test():
            return super(AdminDashboardView, self).dispatch(*args, **kwargs)
        else:
            return redirect(reverse('maintenance_view'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        type = self.request.user.profile.type
        info = SchoolGeneralInfoModel.objects.first()
        if info.school_type == 'mix' and info.separate_school_section:
            academic_info = SchoolAcademicInfoModel.objects.filter(type=type).first()
            context['active_students'] = StudentsModel.objects.filter(status='active', type=type).count()
        else:
            context['active_students'] = StudentsModel.objects.filter(status='active').count()
            academic_info = SchoolAcademicInfoModel.objects.first()
        session = academic_info.session
        term = academic_info.term

        if info.school_type == 'mix' and info.separate_school_section:
            context['notification_list'] = RecentActivityModel.objects.filter(session=session, term=term,
                                           type=type).order_by('id').reverse()[:15]
            context['student_class_list'] = ClassSectionInfoModel.objects.filter(type=type)
        else:
            context['notification_list'] = RecentActivityModel.objects.filter(session=session, term=term).order_by(
                'id').reverse()[:15]

        return context


class AdminMaintenanceView(TemplateView):
    template_name = 'admin_dashboard/maintenance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        return context


def get_last_monday():
    today = date.today()
    last_monday = today - timedelta(days=today.weekday())  # Monday of the current week
    return last_monday


def send_fee_summary_email(request):
    try:
        # Get the current academic session and term
        academic_info = SchoolAcademicInfoModel.objects.first()
        if not academic_info:
            return JsonResponse({"success": False, "message": "No academic session found"}, status=400)

        session = academic_info.session
        term = academic_info.term

        # Get last Monday
        last_monday = get_last_monday()
        today = date.today()

        # Get fee payment summary from last Monday to today
        payments = FeePaymentModel.objects.filter(date__range=[last_monday, today], status='confirmed')
        total_fee_paid = payments.aggregate(total=Sum("amount"), count=Count("id"))

        # Get fee payments for the given session and term
        term_payments = FeePaymentModel.objects.filter(session=session, term=term, status='confirmed')
        total_term_paid = term_payments.aggregate(total=Sum("amount"), count=Count("id"))

        # Group payments by fee type
        fee_summaries = []
        for fee in FeeModel.objects.all():
            fee_payments = payments.filter(fee__fee=fee)
            fee_total = fee_payments.aggregate(total=Sum("amount"), count=Count("id"))
            if fee_total["total"]:
                fee_summaries.append({
                    "name": fee.name,
                    "total_paid": fee_total["total"],
                    "count": fee_total["count"]
                })

        # Prepare email content
        context = {
            "last_monday": last_monday,
            "today": today,
            "fee_summaries": fee_summaries,
            "total_fee_paid": total_fee_paid["total"] or 0,
            "total_payments_made": total_fee_paid["count"] or 0,
            "total_term_paid": total_term_paid["total"] or 0,
            "total_term_payments_made": total_term_paid["count"] or 0,
            "session": session,
            "term": term
        }

        subject = f"White Cloud Academy Fee Payment Summary ({last_monday} - {today})"
        html_message = render_to_string("admin_dashboard/fee_summary.html", context)
        plain_message = strip_tags(html_message)
        from_email = "whitecloudsauto@gmail.com"
        recipient_list = ["nkiruumahi48@gmail.com", "chika.agwu@whitecloudschool.sch.ng",
                          "accounts@whitecloudschool.sch.ng", "og4chy@gmail.com", "chikagwu@icloud.com",
                          "ucheigweonu@gmail.com", "odekeziko@gmail.com"]

        # Send email
        send_mail(subject, plain_message, from_email, recipient_list, html_message=html_message)

        return JsonResponse({"success": True, "message": "Fee summary email sent successfully!"})

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)


def fix_issue(request):
    """
    Sets the 'type' field of all UserProfileModel instances (excluding those
    already with type 'pri') to 'pri' and saves the changes.
    """
    profiles_updated = UserProfileModel.objects.exclude(type='pri').update(type='pri')

    if profiles_updated > 0:
        messages.success(request, f"{profiles_updated} user profiles updated to 'PRIMARY'.")
    else:
        messages.info(request, "No user profiles needed updating to 'PRIMARY'.")
    return HttpResponse('updated')


# ============================================
# views.py
# ============================================


@login_required
@permission_required("student.change_resultmodel", raise_exception=True)
def result_cleanup_view(request):
    """
    Displays the result cleanup page with classes that have results.
    """
    # Get current session and term info
    academic_info = SchoolAcademicInfoModel.objects.first()

    classes_with_results = []

    if academic_info and academic_info.session and academic_info.term:
        # Get all classes that have results for current session/term
        results = ResultModel.objects.filter(
            session=academic_info.session,
            term=academic_info.term,
            result__isnull=False
        ).select_related('student_class').values(
            'student_class__id',
            'student_class__name'
        ).distinct()

        # Count results per class
        for result in results:
            class_id = result['student_class__id']
            class_name = result['student_class__name']

            count = ResultModel.objects.filter(
                session=academic_info.session,
                term=academic_info.term,
                student_class_id=class_id,
                result__isnull=False
            ).count()

            classes_with_results.append({
                'id': class_id,
                'name': class_name,
                'count': count
            })

        # Sort by class name
        classes_with_results.sort(key=lambda x: x['name'])

    context = {
        'academic_info': academic_info,
        'classes_with_results': classes_with_results,
        'total_results': sum(c['count'] for c in classes_with_results)
    }
    return render(request, 'admin_dashboard/result_cleanup.html', context)


@require_POST
@login_required
@permission_required("student.change_resultmodel", raise_exception=True)
def process_result_cleanup_for_class(request):
    """
    Removes blank/zero subjects from result JSON for a specific class.
    Processes one class at a time to avoid timeout.
    """
    class_id = request.POST.get('class_id')

    try:
        # Get current session and term
        academic_info = SchoolAcademicInfoModel.objects.first()

        if not academic_info or not academic_info.session or not academic_info.term:
            return JsonResponse({
                'status': 'error',
                'message': 'No active academic session/term found'
            }, status=400)

        if not class_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Class ID is required'
            }, status=400)

        current_session = academic_info.session
        current_term = academic_info.term

        # Get results for this specific class
        results_to_clean = ResultModel.objects.filter(
            session=current_session,
            term=current_term,
            student_class_id=class_id,
            result__isnull=False
        ).select_related('student', 'student_class')

        cleaned_count = 0
        skipped_count = 0
        total_subjects_removed = 0

        with transaction.atomic():
            for result_obj in results_to_clean:
                if not result_obj.result or not isinstance(result_obj.result, dict):
                    skipped_count += 1
                    continue

                original_result = result_obj.result.copy()
                cleaned_result = {}
                subjects_removed = 0

                # Filter out blank/zero subjects
                for key, subject_data in original_result.items():
                    # Check if subject data is valid
                    if subject_data and isinstance(subject_data, dict):
                        total = subject_data.get('total', 0)

                        # Keep only subjects with non-zero totals
                        try:
                            if float(total) > 0:
                                cleaned_result[key] = subject_data
                            else:
                                subjects_removed += 1
                        except (ValueError, TypeError):
                            # If total is not a valid number, remove it
                            subjects_removed += 1
                    else:
                        # Remove empty/invalid entries
                        subjects_removed += 1

                # Only update if we actually removed something
                if subjects_removed > 0:
                    result_obj.result = cleaned_result
                    result_obj.save()  # This will trigger recalculation in save() method
                    cleaned_count += 1
                    total_subjects_removed += subjects_removed
                else:
                    skipped_count += 1

        return JsonResponse({
            'status': 'success',
            'cleaned': cleaned_count,
            'skipped': skipped_count,
            'subjects_removed': total_subjects_removed
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'An unexpected error occurred: {str(e)}'
        }, status=500)


@login_required
@permission_required("student.change_resultmodel", raise_exception=True)
def process_result_save(request):
    """
    Removes blank/zero subjects from result JSON and resaves to recalculate totals.
    Processes all results for the current session and term.
    """
    try:
        cleaned_count = 0
        result_list = ResultModel.objects.all()
        total = ResultModel.objects.count()

        with transaction.atomic():
            for result in result_list:
                result.save()
                cleaned_count += 1

        return JsonResponse({
            'status': 'success',
            'cleaned': cleaned_count,
            'total': total
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'An unexpected error occurred: {str(e)}'
        }, status=500)
