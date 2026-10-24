"""Resolve a session's explicitly selected Chrome tab without guessing."""
import re


def make_binding(client, state):
    value = state.get('account','')
    if not isinstance(value,str):raise ValueError('Không đọc được tên tài khoản Chrome.')
    account = value.strip()
    if not account or account in ('Chưa hiệu chỉnh', 'Đang đọc trang', 'Không đọc được trang'):
        raise ValueError('Hiệu chỉnh tên tài khoản trong Chrome trước khi gắn phiên.')
    tab = state.get('tab')
    if type(tab) is not int or tab < 0:
        raise ValueError('Không đọc được tab Chrome.')
    instance = state.get('instance', '')
    if instance and not re.fullmatch('[a-f0-9]{32}', instance):
        raise ValueError('Thông tin Chrome không hợp lệ.')
    return dict(instance=instance, tab=tab, account=account, client=client if not instance else '')


def resolve_binding(binding, clients):
    if not binding:
        return None
    matches = []
    for key, state in clients.items():
        if state.get('account') != binding.get('account'):
            continue
        if binding.get('instance'):
            if state.get('instance') != binding['instance']:
                continue
        elif key != binding.get('client') or state.get('tab') != binding.get('tab'):
            continue
        matches.append(key)
    return matches[0] if len(matches) == 1 else None
