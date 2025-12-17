from django.urls import path
from admin_dashboard.views import *

urlpatterns = [
    path('', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('site-is-under-maintenance', AdminMaintenanceView.as_view(), name='maintenance_view'),
    path('send-fee-mail', send_fee_summary_email, name='send_fee_summary_email'),
    path('fix-issue', fix_issue, name='fix_issue'),

    path('result-cleanup/', result_cleanup_view, name='result_cleanup_view'),
    path('result-cleanup/process-class/', process_result_cleanup_for_class, name='result_cleanup_process_class'),
    path('result-cleanup/save/', process_result_save, name='result_save_process'),

]

