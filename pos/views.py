from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json
import logging
from datetime import date, timedelta

try:
    import requests as http_requests
except ImportError:
    http_requests = None

log = logging.getLogger(__name__)

from .models import Category, MenuItem, Table, Order, OrderItem


# ==================== PRINT HELPERS ====================

def _build_main_lines(order) -> list:
    """Build structured lines for full receipt (cashier printer)"""
    items = order.items.select_related('menu_item__category').all()
    now = timezone.localtime(order.created_at).strftime('%Y-%m-%d  %H:%M')

    lines = [
        {'text': '★  فاتورة طلب  ★', 'align': 'center', 'bold': True, 'size': 'large'},
        {'divider': True},
        {'text': f'طلب رقم :  #{order.id}', 'bold': True},
        {'text': f'الطاولة  :  {order.table or "بدون طاولة"}'},
        {'text': f'الوقت    :  {now}'},
        {'text': f'الكاشير  :  {order.cashier.username}'},
        {'divider': True},
    ]

    for item in items:
        lines.append({'text': f'{item.menu_item.name}  x{item.quantity}', 'bold': True})
        lines.append({'text': f'   {item.quantity} × {item.price} = {item.subtotal} ج'})
        if item.notes:
            lines.append({'text': f'   ملاحظة: {item.notes}'})

    lines += [
        {'divider': True},
        {'text': f'الإجمالي:  {order.total} ج', 'bold': True, 'align': 'center', 'size': 'large'},
        {'divider': True},
        {'text': 'شكراً لزيارتكم 🙏', 'align': 'center'},
        {'text': '', },
    ]
    return lines


def _build_kitchen_lines(order, cat_type: str) -> list:
    """Build structured lines for kitchen/bar tickets"""
    items = [i for i in order.items.select_related('menu_item__category').all()
             if i.menu_item.category.category_type == cat_type]
    if not items:
        return []

    label = 'المطبخ 🍽️' if cat_type == 'food' else 'البار 🥤'
    now = timezone.localtime(order.created_at).strftime('%H:%M')

    lines = [
        {'text': f'══  {label}  ══', 'align': 'center', 'bold': True, 'size': 'large'},
        {'text': f'طلب #{order.id}   {now}', 'align': 'center', 'bold': True},
        {'text': f'طاولة: {order.table or "بدون"}', 'align': 'center'},
        {'divider': True},
    ]
    for item in items:
        lines.append({'text': f'{item.menu_item.name}', 'bold': True, 'size': 'large'})
        lines.append({'text': f'   الكمية: {item.quantity}'})
        if item.notes:
            lines.append({'text': f'   ملاحظة: {item.notes}', 'bold': True})
    lines.append({'divider': True})
    return lines


def _send_to_printer(order, open_drawer: bool = False) -> bool:
    """Send order to print service"""
    try:
        payload = {
            'main_lines': _build_main_lines(order),
            'kitchen_lines': _build_kitchen_lines(order, 'food'),
            'bar_lines': _build_kitchen_lines(order, 'drink'),
            'open_drawer': open_drawer,
        }
        if http_requests:
            r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=4)
            return r.status_code == 200 and r.json().get('success', False)
        return False
    except Exception as e:
        log.warning(f'Print error: {e}')
        return False


def _open_drawer_only() -> bool:
    """Open cash drawer without printing"""
    try:
        if http_requests:
            r = http_requests.post(settings.PRINT_SERVICE_URL.replace('/print', '/drawer'), timeout=3)
            return r.json().get('success', False)
        return False
    except Exception as e:
        log.warning(f'Drawer error: {e}')
        return False


# ==================== VIEWS ====================

@login_required
def dashboard(request):
    today = date.today()

    active_orders_today = Order.objects.filter(
        created_at__date=today, status__in=['printed', 'paid']
    ).prefetch_related('items')

    revenue_today = sum(
        item.subtotal for o in active_orders_today for item in o.items.all()
    )

    open_orders = Order.objects.filter(status='open').count()
    printed_orders = Order.objects.filter(status='printed').count()
    total_today = Order.objects.filter(
        created_at__date=today
    ).exclude(status='cancelled').count()

    recent_orders = (
        Order.objects
        .filter(status__in=['open', 'printed'])
        .select_related('table', 'cashier')
        .prefetch_related('items__menu_item')
        .order_by('-created_at')[:12]
    )

    return render(request, 'pos/dashboard.html', {
        'revenue_today': revenue_today,
        'open_orders': open_orders,
        'printed_orders': printed_orders,
        'total_today': total_today,
        'recent_orders': recent_orders,
    })


@login_required
def new_order(request):
    categories = Category.objects.prefetch_related('items').all()
    tables = Table.objects.filter(is_active=True)
    return render(request, 'pos/new_order.html', {
        'categories': categories,
        'tables': tables,
    })


@login_required
@require_POST
def preview_order(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        table_id = data.get('table_id')
        notes = data.get('notes', '')

        if not items_data:
            return JsonResponse({'success': False, 'error': 'أضف منتجات أولاً'})

        preview_items = []
        total = 0
        for item_data in items_data:
            mi = get_object_or_404(MenuItem, id=item_data['id'])
            qty = int(item_data.get('quantity', 1))
            subtotal = mi.price * qty
            total += subtotal
            preview_items.append({
                'name': mi.name,
                'qty': qty,
                'price': float(mi.price),
                'subtotal': float(subtotal),
                'cat_type': mi.category.category_type,
                'notes': item_data.get('notes', ''),
            })

        table_label = 'بدون طاولة'
        if table_id:
            try:
                table_label = str(Table.objects.get(id=table_id))
            except Table.DoesNotExist:
                pass

        return JsonResponse({
            'success': True,
            'items': preview_items,
            'total': float(total),
            'table': table_label,
            'notes': notes,
            'time': timezone.localtime(timezone.now()).strftime('%Y-%m-%d  %H:%M'),
            'cashier': request.user.get_full_name() or request.user.username,
        })
    except Exception as e:
        log.error(f'preview_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
        table_id = data.get('table_id')
        items_data = data.get('items', [])
        notes = data.get('notes', '')
        open_drawer = data.get('open_drawer', True)

        if not items_data:
            return JsonResponse({'success': False, 'error': 'أضف منتجات أولاً'})

        order = Order.objects.create(
            table_id=table_id if table_id else None,
            cashier=request.user,
            notes=notes,
            status='open',
        )

        for item_data in items_data:
            mi = get_object_or_404(MenuItem, id=item_data['id'])
            OrderItem.objects.create(
                order=order,
                menu_item=mi,
                quantity=int(item_data.get('quantity', 1)),
                price=mi.price,
                notes=item_data.get('notes', ''),
            )

        print_ok = _send_to_printer(order, open_drawer=open_drawer)

        order.status = 'printed'
        order.printed_at = timezone.now()
        order.save()

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'print_success': print_ok,
        })
    except Exception as e:
        log.error(f'create_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def orders_list(request):
    status_filter = request.GET.get('status', 'active')
    date_filter = request.GET.get('date', str(date.today()))
    search_query = request.GET.get('search', '').strip()

    qs = Order.objects.filter(
        created_at__date=date_filter
    ).select_related('table', 'cashier').prefetch_related('items__menu_item').order_by('-created_at')

    if status_filter == 'active':
        qs = qs.filter(status__in=['open', 'printed'])
    elif status_filter == 'printed':
        qs = qs.filter(status='printed')
    elif status_filter == 'cancelled':
        qs = qs.filter(status='cancelled')

    if search_query:
        qs = qs.filter(id__icontains=search_query)

    paginator = Paginator(qs, 15)
    try:
        orders = paginator.page(request.GET.get('page', 1))
    except (EmptyPage, PageNotAnInteger):
        orders = paginator.page(1)

    day_stats = {
        'active': Order.objects.filter(created_at__date=date_filter, status__in=['open', 'printed']).count(),
        'printed': Order.objects.filter(created_at__date=date_filter, status='printed').count(),
        'cancelled': Order.objects.filter(created_at__date=date_filter, status='cancelled').count(),
        'total': Order.objects.filter(created_at__date=date_filter).exclude(status='cancelled').count(),
    }

    return render(request, 'pos/orders_list.html', {
        'orders': orders,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'search_query': search_query,
        'day_stats': day_stats,
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('table', 'cashier')
        .prefetch_related('items__menu_item__category'),
        id=order_id
    )
    return render(request, 'pos/order_detail.html', {'order': order})


@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status in ['open', 'printed']:
        order.status = 'cancelled'
        order.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'لا يمكن إلغاء هذا الطلب'})


@login_required
@require_POST
def reprint_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    data = json.loads(request.body) if request.body else {}
    open_drawer = data.get('open_drawer', False)
    ok = _send_to_printer(order, open_drawer=open_drawer)
    return JsonResponse({'success': ok})


@login_required
@require_POST
def open_drawer(request):
    ok = _open_drawer_only()
    return JsonResponse({'success': ok})


@login_required
def mark_paid(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status in ['printed', 'paid']:
        order.status = 'paid'
        order.paid_at = timezone.now()
        order.save()
    return redirect('orders_list')


@login_required
def reports(request):
    today = date.today()
    period = request.GET.get('period', 'week')

    if period == 'today':
        start_date = end_date = today
    elif period == 'month':
        start_date = today.replace(day=1)
        end_date = today
    else:  # week default
        start_date = today - timedelta(days=6)
        end_date = today

    orders = Order.objects.filter(
        created_at__date__range=[start_date, end_date],
        status__in=['printed', 'paid']
    ).prefetch_related('items')

    total_revenue = sum(item.subtotal for o in orders for item in o.items.all())
    total_orders = orders.count()
    avg_order = total_revenue / total_orders if total_orders else 0

    daily_data = []
    delta = (end_date - start_date).days + 1
    for i in range(delta):
        d = start_date + timedelta(days=i)
        day_orders = orders.filter(created_at__date=d)
        rev = sum(item.subtotal for o in day_orders for item in o.items.all())
        daily_data.append({
            'date': d.strftime('%m/%d'),
            'revenue': float(rev),
            'count': day_orders.count(),
        })

    top_items = (
        OrderItem.objects
        .filter(
            order__created_at__date__range=[start_date, end_date],
            order__status__in=['printed', 'paid'],
        )
        .values('menu_item__name', 'menu_item__category__name')
        .annotate(total_qty=Sum('quantity'), total_rev=Sum('price'))
        .order_by('-total_qty')[:10]
    )

    return render(request, 'pos/reports.html', {
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_order': avg_order,
        'daily_data': json.dumps(daily_data),
        'top_items': top_items,
        'period': period,
    })