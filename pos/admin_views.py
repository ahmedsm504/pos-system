from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Case, IntegerField, Sum, Count, Q, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.contrib import messages
import json
from datetime import date, timedelta
from decimal import Decimal

from .models import (Category, MenuItem, Table, Waiter, DeliveryDriver,
                     Order, OrderItem, InventoryEntry, Shift, CashierProfile)


def admin_required(view_func):
    decorated = login_required(user_passes_test(lambda u: u.is_staff)(view_func))
    return decorated


def _item_form_categories():
    return (
        Category.objects.filter(is_active=True)
        .annotate(
            _type_sort=Case(
                When(category_type='food', then=0),
                When(category_type='drink', then=1),
                default=2,
                output_field=IntegerField(),
            )
        )
        .order_by('_type_sort', 'order', 'name')
    )


def _item_form_category_groups():
    """أكل ثم مشروبات ثم أخرى — لقوائم optgroup في نموذج المنتج."""
    order = [('food', 'أكل'), ('drink', 'مشروبات'), ('other', 'أخرى')]
    buckets = {code: [] for code, _ in order}
    for c in _item_form_categories():
        key = c.category_type if c.category_type in buckets else 'other'
        buckets[key].append(c)
    return [(code, label, buckets[code]) for code, label in order]


# ══════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def dashboard(request):
    today = date.today()
    orders_today = Order.objects.filter(created_at__date=today).exclude(status='cancelled')
    revenue_today = sum(o.total for o in orders_today.filter(status__in=['printed','completed']))
    expenses_today = InventoryEntry.objects.filter(date=today).aggregate(t=Sum('total_cost'))['t'] or 0
    profit_today = revenue_today - expenses_today

    top_item = (OrderItem.objects
                .filter(order__created_at__date=today, order__status__in=['printed','completed'])
                .values('menu_item__name')
                .annotate(qty=Sum('quantity'))
                .order_by('-qty').first())

    recent_orders = Order.objects.filter(created_at__date=today).select_related('cashier','table','waiter','driver')[:8]

    return render(request, 'pos/admin/dashboard.html', {
        'revenue_today':  revenue_today,
        'expenses_today': expenses_today,
        'profit_today':   profit_today,
        'orders_count':   orders_today.count(),
        'top_item':       top_item,
        'recent_orders':  recent_orders,
        'open_orders':    Order.objects.filter(status__in=['open','printed']).count(),
    })


# ══════════════════════════════════════════════════════════════════════════
#  MENU
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def menu_list(request):
    categories = list(
        Category.objects.prefetch_related('items').order_by('order', 'name')
    )
    menu_stats = {
        'all': {'categories': 0, 'items': 0},
        'food': {'categories': 0, 'items': 0},
        'drink': {'categories': 0, 'items': 0},
        'other': {'categories': 0, 'items': 0},
    }
    for c in categories:
        n_items = len(c.items.all())
        menu_stats['all']['categories'] += 1
        menu_stats['all']['items'] += n_items
        t = c.category_type
        if t in menu_stats:
            menu_stats[t]['categories'] += 1
            menu_stats[t]['items'] += n_items
    return render(
        request,
        'pos/admin/menu.html',
        {'categories': categories, 'menu_stats': menu_stats},
    )


@admin_required
def category_add(request):
    if request.method == 'POST':
        Category.objects.create(
            name=request.POST['name'],
            category_type=request.POST['category_type'],
            order=request.POST.get('order', 0),
        )
        messages.success(request, 'تم إضافة التصنيف')
        return redirect('admin_menu')
    return render(request, 'pos/admin/category_form.html', {'title': 'إضافة تصنيف'})


@admin_required
def category_edit(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        cat.name = request.POST['name']
        cat.category_type = request.POST['category_type']
        cat.order = request.POST.get('order', 0)
        cat.is_active = 'is_active' in request.POST
        cat.save()
        messages.success(request, 'تم تعديل التصنيف')
        return redirect('admin_menu')
    return render(request, 'pos/admin/category_form.html', {'title': 'تعديل تصنيف', 'obj': cat})


@admin_required
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        cat.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


@admin_required
def item_add(request):
    if request.method == 'POST':
        MenuItem.objects.create(
            category_id=request.POST['category'],
            name=request.POST['name'],
            price=request.POST['price'],
            order=request.POST.get('order', 0),
            description=request.POST.get('description', ''),
        )
        messages.success(request, 'تم إضافة المنتج')
        return redirect('admin_menu')
    return render(
        request,
        'pos/admin/item_form.html',
        {'title': 'إضافة منتج', 'category_groups': _item_form_category_groups()},
    )


@admin_required
def item_edit(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        item.category_id  = request.POST['category']
        item.name         = request.POST['name']
        item.price        = request.POST['price']
        item.order        = request.POST.get('order', 0)
        item.description  = request.POST.get('description', '')
        item.is_available = 'is_available' in request.POST
        item.save()
        messages.success(request, 'تم تعديل المنتج')
        return redirect('admin_menu')
    return render(
        request,
        'pos/admin/item_form.html',
        {
            'title': 'تعديل منتج',
            'obj': item,
            'category_groups': _item_form_category_groups(),
        },
    )


@admin_required
def item_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        item.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  CASHIERS
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def cashier_list(request):
    cashiers = User.objects.filter(is_staff=False).select_related('cashier_profile')
    return render(request, 'pos/admin/cashiers.html', {'cashiers': cashiers})


@admin_required
def cashier_add(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        full_name = request.POST.get('full_name', '')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'اسم المستخدم موجود بالفعل')
        else:
            user = User.objects.create_user(
                username=username, password=password,
                first_name=full_name.split()[0] if full_name else '',
                last_name=' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else '',
            )
            CashierProfile.objects.create(
                user=user,
                phone=request.POST.get('phone', ''),
                can_view_totals='can_view_totals' in request.POST,
                can_view_history='can_view_history' in request.POST,
                can_open_drawer='can_open_drawer' in request.POST,
            )
            messages.success(request, f'تم إضافة الكاشير {username}')
            return redirect('admin_cashiers')
    return render(request, 'pos/admin/cashier_form.html', {'title': 'إضافة كاشير'})


@admin_required
def cashier_edit(request, pk):
    user = get_object_or_404(User, pk=pk, is_staff=False)
    profile, _ = CashierProfile.objects.get_or_create(user=user)
    if request.method == 'POST':
        user.username   = request.POST['username']
        full_name       = request.POST.get('full_name', '')
        user.first_name = full_name.split()[0] if full_name else ''
        user.last_name  = ' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else ''
        if request.POST.get('password'):
            user.set_password(request.POST['password'])
        user.save()
        profile.phone            = request.POST.get('phone', '')
        profile.can_view_totals  = 'can_view_totals'  in request.POST
        profile.can_view_history = 'can_view_history' in request.POST
        profile.can_open_drawer  = 'can_open_drawer'  in request.POST
        profile.save()
        messages.success(request, 'تم تعديل بيانات الكاشير')
        return redirect('admin_cashiers')
    return render(request, 'pos/admin/cashier_form.html', {'title': 'تعديل كاشير', 'obj': user, 'profile': profile})


@admin_required
def cashier_delete(request, pk):
    user = get_object_or_404(User, pk=pk, is_staff=False)
    if request.method == 'POST':
        user.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  TABLES
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def tables_list(request):
    tables = Table.objects.all()
    return render(request, 'pos/admin/tables.html', {'tables': tables})


@admin_required
def table_add(request):
    if request.method == 'POST':
        try:
            Table.objects.create(number=request.POST['number'], name=request.POST.get('name', ''))
            messages.success(request, 'تم إضافة الطاولة')
        except Exception:
            messages.error(request, 'رقم الطاولة موجود بالفعل')
        return redirect('admin_tables')
    return render(request, 'pos/admin/table_form.html', {'title': 'إضافة طاولة'})


@admin_required
def table_edit(request, pk):
    table = get_object_or_404(Table, pk=pk)
    if request.method == 'POST':
        table.name      = request.POST.get('name', '')
        table.is_active = 'is_active' in request.POST
        table.save()
        messages.success(request, 'تم تعديل الطاولة')
        return redirect('admin_tables')
    return render(request, 'pos/admin/table_form.html', {'title': 'تعديل طاولة', 'obj': table})


@admin_required
def table_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(Table, pk=pk).delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  WAITERS
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def waiter_list(request):
    return render(request, 'pos/admin/waiters.html', {'waiters': Waiter.objects.all()})


@admin_required
def waiter_add(request):
    if request.method == 'POST':
        Waiter.objects.create(name=request.POST['name'], phone=request.POST.get('phone', ''))
        messages.success(request, 'تم إضافة الويتر')
        return redirect('admin_waiters')
    return render(request, 'pos/admin/waiter_form.html', {'title': 'إضافة ويتر'})


@admin_required
def waiter_edit(request, pk):
    w = get_object_or_404(Waiter, pk=pk)
    if request.method == 'POST':
        w.name      = request.POST['name']
        w.phone     = request.POST.get('phone', '')
        w.is_active = 'is_active' in request.POST
        w.save()
        messages.success(request, 'تم تعديل الويتر')
        return redirect('admin_waiters')
    return render(request, 'pos/admin/waiter_form.html', {'title': 'تعديل ويتر', 'obj': w})


@admin_required
def waiter_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(Waiter, pk=pk).delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  DELIVERY DRIVERS
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def driver_list(request):
    # Stats per driver
    period = request.GET.get('period', '30')
    try: days = int(period)
    except: days = 30
    start = date.today() - timedelta(days=days)
    drivers = DeliveryDriver.objects.all()
    driver_stats = []
    for d in drivers:
        orders = Order.objects.filter(driver=d, created_at__date__gte=start, status__in=['printed','completed'])
        rev = sum(o.total for o in orders)
        driver_stats.append({'driver': d, 'count': orders.count(), 'revenue': rev})
    return render(request, 'pos/admin/drivers.html', {'driver_stats': driver_stats, 'period': period})


@admin_required
def driver_add(request):
    if request.method == 'POST':
        DeliveryDriver.objects.create(name=request.POST['name'], phone=request.POST['phone'])
        messages.success(request, 'تم إضافة الطيار')
        return redirect('admin_drivers')
    return render(request, 'pos/admin/driver_form.html', {'title': 'إضافة طيار'})


@admin_required
def driver_edit(request, pk):
    d = get_object_or_404(DeliveryDriver, pk=pk)
    if request.method == 'POST':
        d.name = request.POST['name']; d.phone = request.POST['phone']
        d.is_active = 'is_active' in request.POST; d.save()
        messages.success(request, 'تم تعديل بيانات الطيار')
        return redirect('admin_drivers')
    return render(request, 'pos/admin/driver_form.html', {'title': 'تعديل طيار', 'obj': d})


@admin_required
def driver_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(DeliveryDriver, pk=pk).delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════════════════════════════════

_AR_MONTHS = (
    (1, 'يناير'),
    (2, 'فبراير'),
    (3, 'مارس'),
    (4, 'أبريل'),
    (5, 'مايو'),
    (6, 'يونيو'),
    (7, 'يوليو'),
    (8, 'أغسطس'),
    (9, 'سبتمبر'),
    (10, 'أكتوبر'),
    (11, 'نوفمبر'),
    (12, 'ديسمبر'),
)


@admin_required
def inventory_list(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    raw_start = (request.GET.get('start') or '').strip()
    raw_end = (request.GET.get('end') or '').strip()

    start_d = parse_date(raw_start) if raw_start else None
    end_d = parse_date(raw_end) if raw_end else None

    if raw_start and start_d is None:
        messages.warning(request, 'تاريخ البداية غير صالح. تم استخدام أول الشهر الحالي.')
        start_d = month_start
    elif start_d is None:
        start_d = month_start

    if raw_end and end_d is None:
        messages.warning(request, 'تاريخ النهاية غير صالح. تم استخدام اليوم.')
        end_d = today
    elif end_d is None:
        end_d = today

    if start_d > end_d:
        start_d, end_d = end_d, start_d

    qs = (
        InventoryEntry.objects.filter(date__range=[start_d, end_d])
        .select_related('added_by')
        .order_by('-date', '-id')
    )
    total_cost = qs.aggregate(t=Sum('total_cost'))['t'] or 0
    entries = list(qs)
    year_now = today.year
    year_options = list(range(year_now - 4, year_now + 2))
    week_start = today - timedelta(days=today.weekday())
    thirty_back = today - timedelta(days=29)

    return render(
        request,
        'pos/admin/inventory.html',
        {
            'entries': entries,
            'total_cost': total_cost,
            'start_date': start_d,
            'end_date': end_d,
            'ar_months': _AR_MONTHS,
            'year_options': year_options,
            'days_range': list(range(1, 32)),
            'today_iso': today.strftime('%Y-%m-%d'),
            'month_start_iso': month_start.strftime('%Y-%m-%d'),
            'week_start_iso': week_start.strftime('%Y-%m-%d'),
            'thirty_back_iso': thirty_back.strftime('%Y-%m-%d'),
        },
    )


@admin_required
def inventory_add(request):
    today = timezone.localdate()
    if request.method == 'POST':
        raw_d = (request.POST.get('date') or '').strip()
        entry_date = parse_date(raw_d) if raw_d else today
        if raw_d and entry_date is None:
            entry_date = today
        InventoryEntry.objects.create(
            name=request.POST['name'],
            quantity=request.POST['quantity'],
            unit=request.POST.get('unit', ''),
            total_cost=request.POST['total_cost'],
            date=entry_date,
            notes=request.POST.get('notes', ''),
            added_by=request.user,
        )
        messages.success(request, 'تم إضافة الوارد')
        return redirect('admin_inventory')
    return render(
        request,
        'pos/admin/inventory_form.html',
        {
            'today': today,
            'ar_months': _AR_MONTHS,
            'year_options': list(range(today.year - 4, today.year + 2)),
            'days_range': list(range(1, 32)),
        },
    )


@admin_required
def inventory_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(InventoryEntry, pk=pk).delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ══════════════════════════════════════════════════════════════════════════
#  REPORTS / PROFITS
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def reports(request):
    period = request.GET.get('period', 'week')
    today  = date.today()

    if period == 'today':
        start = end = today
    elif period == 'month':
        start = today.replace(day=1); end = today
    else:
        start = today - timedelta(days=6); end = today

    orders = Order.objects.filter(
        created_at__date__range=[start, end],
        status__in=['printed', 'completed']
    ).prefetch_related('items')

    total_revenue = sum(o.total for o in orders)
    total_orders  = orders.count()

    # breakdown: dine vs delivery
    dine_orders    = orders.filter(order_type='dine_in')
    delivery_orders = orders.filter(order_type='delivery')
    dine_revenue   = sum(o.total for o in dine_orders)
    delivery_revenue = sum(o.total for o in delivery_orders)

    # expenses
    expenses = InventoryEntry.objects.filter(date__range=[start, end])
    total_expenses = expenses.aggregate(t=Sum('total_cost'))['t'] or 0
    profit = total_revenue - total_expenses

    # daily data
    daily = []
    delta = (end - start).days + 1
    for i in range(delta):
        d = start + timedelta(days=i)
        day_orders = orders.filter(created_at__date=d)
        rev = sum(o.total for o in day_orders)
        exp = expenses.filter(date=d).aggregate(t=Sum('total_cost'))['t'] or 0
        daily.append({'date': d.strftime('%m/%d'), 'revenue': float(rev), 'expenses': float(exp), 'count': day_orders.count()})

    # top items
    top_items = (OrderItem.objects
        .filter(order__in=orders)
        .values('menu_item__name', 'menu_item__category__name')
        .annotate(qty=Sum('quantity'), rev=Sum('price'))
        .order_by('-qty')[:10])

    # cashier stats
    cashier_stats = []
    cashiers = User.objects.filter(is_staff=False)
    for c in cashiers:
        co = orders.filter(cashier=c)
        cr = sum(o.total for o in co)
        cashier_stats.append({'cashier': c, 'count': co.count(), 'revenue': cr})
    cashier_stats.sort(key=lambda x: x['revenue'], reverse=True)

    import json
    return render(request, 'pos/admin/reports.html', {
        'period': period, 'start': start, 'end': end,
        'total_revenue': total_revenue, 'total_orders': total_orders,
        'dine_revenue': dine_revenue, 'delivery_revenue': delivery_revenue,
        'dine_count': dine_orders.count(), 'delivery_count': delivery_orders.count(),
        'total_expenses': total_expenses, 'profit': profit,
        'daily_json': json.dumps(daily),
        'top_items': top_items,
        'cashier_stats': cashier_stats,
    })


# ══════════════════════════════════════════════════════════════════════════
#  HISTORY
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def history(request):
    today = timezone.localdate()
    raw = (request.GET.get('date') or '').strip()
    selected = parse_date(raw) if raw else None
    if raw and selected is None:
        messages.warning(request, 'صيغة التاريخ غير صالحة. تم عرض تاريخ اليوم.')
        selected = today
    elif selected is None:
        selected = today

    orders = list(
        Order.objects.filter(created_at__date=selected)
        .select_related('cashier', 'table', 'waiter', 'driver')
        .prefetch_related('items__menu_item')
        .order_by('-created_at')
    )
    day_revenue = sum(
        o.total for o in orders if o.status in ('printed', 'completed')
    )
    year_now = today.year
    year_options = list(range(year_now - 4, year_now + 2))
    return render(
        request,
        'pos/admin/history.html',
        {
            'orders': orders,
            'selected_date': selected,
            'day_revenue': day_revenue,
            'ar_months': _AR_MONTHS,
            'year_options': year_options,
            'days_range': list(range(1, 32)),
            'today_iso': today.strftime('%Y-%m-%d'),
            'prev_date': selected - timedelta(days=1),
            'next_date': selected + timedelta(days=1),
        },
    )


@admin_required
def order_history_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('cashier','table','waiter','driver')
                     .prefetch_related('items__menu_item__category'),
        id=order_id
    )
    return render(request, 'pos/admin/order_detail.html', {'order': order})


# ══════════════════════════════════════════════════════════════════════════
#  SHIFTS
# ══════════════════════════════════════════════════════════════════════════

@admin_required
def shifts_list(request):
    shifts = Shift.objects.select_related('cashier').order_by('-start_time')[:50]
    return render(request, 'pos/admin/shifts.html', {'shifts': shifts})
