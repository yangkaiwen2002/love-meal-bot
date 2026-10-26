"""Shared, link-free presentation for Life Butler's Feishu Card 2.0 pushes."""
import datetime
import html
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Hong_Kong')

def plain(value):
    return {'tag': 'plain_text', 'content': str(value)}

def safe(value):
    return html.escape(str(value)).replace('*', '&#42;').replace('[', '&#91;').replace(']', '&#93;')

def text(value, size='normal', **kwargs):
    return {'tag': 'markdown', 'content': value, 'text_size': size, **kwargs}

def muted(value):
    return text('<font color="grey">' + safe(value) + '</font>', 'notation')

def column(elements, width='weighted', **kwargs):
    return {'tag': 'column', 'width': width, 'weight': 1, 'vertical_spacing': '8px', 'elements': elements, **kwargs}

def row(columns, **kwargs):
    return {'tag': 'column_set', 'flex_mode': 'none', 'horizontal_spacing': '12px', 'columns': columns, **kwargs}

def panel(elements, background='cus-soft'):
    return {'tag':'interactive_container','width':'fill','background_style':background,'corner_radius':'12px','padding':'12px','vertical_spacing':'8px','elements':elements}

def shell(title, elements):
    return {
        'schema': '2.0',
        'config': {
            'update_multi': True, 'width_mode': 'compact', 'enable_forward': False,
            'summary': {'content': title},
            'style': {'color': {
                'cus-rose': {'light_mode': 'rgba(142,78,89,1)', 'dark_mode': 'rgba(225,165,175,1)'},
                'cus-soft': {'light_mode': 'rgba(249,242,241,1)', 'dark_mode': 'rgba(55,41,44,1)'},
            }},
        },
        'body': {'direction': 'vertical', 'padding': '16px', 'vertical_spacing': '12px', 'elements': elements},
    }

def heading(title, caption, right=None):
    cols = [column([text('**' + safe(title) + '**'), muted(caption)])]
    if right is not None:
        cols.append(column([right], width='auto', vertical_align='center'))
    return row(cols)

def morning_card(day=None, preview=False):
    day = day or datetime.datetime.now(TZ).strftime('%m月%d日')
    return shell('早安 · 记得抹药，也记得吃早餐', [
        heading('早安，小日常', ('样式预览 · ' if preview else '') + day + ' · 09:00'),
        panel([text('**今天，也要好好照顾自己。**', 'heading-3'), muted('把关心，放在一天的开始。')]),
        row([
            column([text('**记得抹药**'), muted('给自己一点细心照顾')], padding='4px'),
            column([text('**好好吃早餐**'), muted('忙碌前，先吃点喜欢的')], padding='4px'),
        ]),
        muted('不急不赶，愿你今天顺顺利利。'),
    ])

def news_card(selected, source_date, preview=False):
    # Retain the exact source edition in the collapsed original; never label it as today's news.
    entries = []
    for line in selected.splitlines():
        match = re.match(r'^\s*\d+[.)]\s*\[([^\]]+)\].*?\[([^\]]+)\]\((https?://[^\s]+)\)', line)
        if match:
            entries.append(match.groups())
    total_match = re.search(r'共\s*(\d+)\s*条', selected)
    total = int(total_match.group(1)) if total_match else len(entries)
    source_date = str(source_date)
    elements = [heading('AI 每日精选', ('样式预览 · ' if preview else '') + 'AI 资讯助手 · 原始发布 ' + source_date)]
    if entries:
        for index, (source, title, url) in enumerate(entries[:3], 1):
            elements.append(panel([
                text('**' + f'{index:02d}  ' + safe(title) + '**'),
                text('[' + safe(source) + ' · 阅读原文](' + url + ')', 'notation'),
            ], 'cus-soft' if index == 1 else 'default'))
    else:
        elements.append(panel([text('**这一期新鲜事，已经送达。**'), muted('展开下方原始榜单，查看全部资讯。')]))
    elements.append({
        'tag': 'collapsible_panel', 'expanded': False,
        'header': {'title': plain(f'展开全部 {total} 条 · 原始榜单' if entries else '展开原始榜单'), 'icon_position': 'right'},
        'border': {'color': 'grey-200', 'corner_radius': '8px'}, 'padding': '12px',
        'elements': [text(selected.strip())],
    })
    return shell('AI 每日精选 · 原始发布 ' + source_date, elements)
