from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
import json

from .models import CashierProfile, Shift


def login_view(request):
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # open shift for cashier
            if not user.is_staff:
                Shift.objects.get_or_create(cashier=user, status='open')
            return redirect('home')
        else:
            error = 'اسم المستخدم أو كلمة السر غلط'
    return render(request, 'pos/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def home(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    return redirect('cashier_dashboard')


@require_POST
def admin_verify(request):
    """AJAX — verify admin credentials for sensitive actions"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '')
        password = data.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user and user.is_staff:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'بيانات المدير غلط'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
