from django import template
from django.utils import timezone

register = template.Library()


@register.filter(name='time12')
def time12(value):
    """12h Arabic time: 8:30 م"""
    if value is None:
        return ''
    try:
        local = timezone.localtime(value)
    except Exception:
        local = value
    h = local.hour
    period = 'ص' if h < 12 else 'م'
    h12 = h % 12 or 12
    return f'{h12}:{local.minute:02d} {period}'


@register.filter(name='datetime12')
def datetime12(value, fmt='d/m'):
    """Date + 12h Arabic time: 10/04 8:30 م"""
    if value is None:
        return ''
    try:
        local = timezone.localtime(value)
    except Exception:
        local = value
    h = local.hour
    period = 'ص' if h < 12 else 'م'
    h12 = h % 12 or 12
    from django.utils.dateformat import format as df
    date_part = df(local, fmt)
    return f'{date_part} {h12}:{local.minute:02d} {period}'
