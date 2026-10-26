"""Feishu-native meal decisions, shared preferences, favorites and recent choices."""
import datetime
from contextlib import contextmanager
import json
import os
import pathlib
import random
import re
import signal
import sqlite3
import subprocess
import sys
from push_ui import plain as txt, text as md, muted, safe, row, column, panel, shell, heading, TZ

BASE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get('LOVE_MEAL_DATA_DIR', str(BASE / 'data'))).expanduser()
ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = pathlib.Path(os.environ.get('LOVE_MEAL_CONFIG', str(BASE / 'config.json'))).expanduser()
settings = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
CHAT = settings.get('chat_id', '')
MEMBERS = set(settings.get('member_ids', []))
CLI = os.environ.get('LARK_CLI', 'lark-cli')
MENU = json.loads((BASE / 'card-menu.json').read_text())
APP = 'love-meal-v1'


def words(value):
    return list(dict.fromkeys(x.strip() for x in re.split(r'[,，、\s]+', value) if x.strip()))


def eligible(excluded, pool='all', favorites=()):
    avoid = [x.lower() for x in words(excluded)]
    return [dish for dish in MENU if (pool != 'favorites' or dish['name'] in favorites)
            and not any(x in (dish['name'] + ',' + dish['ingredients']).lower() for x in avoid)]


def behavior(action, **value):
    return [{'type': 'callback', 'value': {'app': APP, 'action': action, **value}}]


def button(label, action, kind='text', icon=None, **value):
    result = {'tag': 'button', 'text': txt(label), 'type': kind, 'size': 'medium',
              'behaviors': behavior(action, **value)}
    if icon:
        result['icon'] = {'tag': 'standard_icon', 'token': icon}
    return result


def primary(label, action, **value):
    # A native interactive container permits the same callback with our brand color.
    return {'tag': 'interactive_container', 'width': 'fill', 'background_style': 'cus-rose',
            'corner_radius': '8px', 'padding': '8px 12px', 'behaviors': behavior(action, **value),
            'elements': [md('<font color="white">**' + safe(label) + '**</font>', text_align='center')]}


def actions(*items):
    return row([column([item]) for item in items])


def card(result=None, settings=False, excluded='', notice='', *, view='home', pool='all', favorites=(), recent=(), confirmed=False, meta=None):
    meta = meta or {}
    view = 'settings' if settings else view
    date = meta.get('day', '')
    meal = {'lunch': '午餐', 'dinner': '晚餐'}.get(meta.get('meal'), '这一餐')
    caption = ' · '.join(x for x in (date, '双人共享') if x)
    elements = [heading(meal + '提案' if meal != '这一餐' else '吃饭小抽签', caption,
                        button('返回', 'back') if view != 'home' else button('设置', 'settings', icon='setting_outlined'))]
    choices = eligible(excluded, pool, favorites)
    if view == 'settings':
        elements.append(panel([md('**吃什么，先听你们的。**', 'heading-3'), muted('偏好在群内共享，保存后立即用于下一次抽签。')]))
        elements.append({'tag': 'form', 'name': 'meal_settings', 'elements': [
            {'tag': 'input', 'name': 'excluded', 'label': txt('不想吃的菜 / 食材'),
             'placeholder': txt('例如：虾、牛肉、辣椒'), 'default_value': excluded,
             'max_length': 300, 'width': 'fill'},
            {'tag': 'select_static', 'name': 'pool', 'width': 'fill',
             'placeholder': txt('从哪里抽菜'), 'initial_option': pool,
             'options': [{'text': txt('全部菜单 · 50 道'), 'value': 'all'},
                         {'text': txt('只抽收藏 · ' + str(len(favorites)) + ' 道'), 'value': 'favorites'}]},
            {'tag': 'button', 'name': 'save_meal_settings', 'text': txt('保存偏好'),
             'type': 'default', 'size': 'medium', 'width': 'fill', 'form_action_type': 'submit'},
        ]})
        elements.append(muted('食材用顿号分隔，留空可取消忌口。具体配料请向商家确认。'))
        if pool == 'favorites' and not choices:
            elements.append(button('改从全部菜单抽', 'use_all', kind='default'))
    elif view == 'favorites':
        elements.append(panel([md('**你们喜欢的味道**', 'heading-3'), muted(f'已收藏 {len(favorites)} 道 · 每页 5 道')]))
        page = max(0, int(meta.get('page', 0)))
        favorite_dishes = [d for d in MENU if d['name'] in favorites]
        max_page = max(0, (len(favorite_dishes) - 1) // 5)
        page = min(page, max_page)
        allowed = {d['name'] for d in eligible(excluded)}
        for dish in favorite_dishes[page * 5:(page + 1) * 5]:
            controls = button('看看这道', 'choose', kind='default', dish=dish['name'])
            if dish['name'] not in allowed:
                controls['disabled'] = True
                controls['disabled_tips'] = txt('与当前忌口冲突，调整设置后再选择')
            elements.append(row([column([md('**' + safe(dish['name']) + '**'),
                                         muted('与忌口冲突' if dish['name'] not in allowed else dish['ingredients'].replace(',', ' · '))]),
                                 column([controls], width='auto')]))
        if not favorites:
            elements.append(muted('还没有收藏。先抽一道菜，再点「收藏」，下次就更好选。'))
        if len(favorite_dishes) > 5:
            elements.append(actions(button('上一页', 'favorites', page=max(0, page - 1)),
                                    button(f'{page + 1}/{max_page + 1} · 下一页', 'favorites', page=min(max_page, page + 1))))
    elif view == 'recent':
        elements.append(panel([md('**最近，决定吃的菜**', 'heading-3'), muted('只记录点过「就吃这道」的选择，未确认的抽签不计入。')]))
        for item in recent[:5]:
            dish = item['dish']
            detail = ' · '.join(x for x in (item['day'], {'lunch':'午餐','dinner':'晚餐'}.get(item['meal'], '加餐')) if x)
            elements.append(row([column([md('**' + safe(dish['name']) + '**'), muted(detail)]),
                                 column([button('再选一次', 'choose', kind='default', dish=dish['name'])], width='auto')]))
        if not recent:
            elements.append(muted('还没有确定的餐单。下一次决定好了，点一下「就吃这道」。'))
    else:
        if result:
            saved = result['name'] in favorites
            label = '本餐已决定' if confirmed else '这一顿，推荐给你们'
            elements.append(panel([muted(label), md('**' + safe(result['name']) + '**', 'heading-2'),
                                   muted('主要食材 · ' + result['ingredients'].replace(',', ' · '))]))
            if confirmed:
                elements.append(actions(button('重新选择', 'draw', kind='default'),
                                        button('已收藏 · 取消' if saved else '收藏这道', 'favorite', expected_dish=result['name'])))
            else:
                elements.append(actions(primary('就吃这道', 'confirm', expected_dish=result['name']), button('换一道', 'draw', kind='default')))
                elements.append(button('已收藏 · 取消' if saved else '收藏这道', 'favorite', expected_dish=result['name']))
        else:
            intro = [md('**这一顿，吃点喜欢的。**', 'heading-3'), muted('让小管家选一选，合心意再决定。')]
            image = ROOT / 'meal-hero-key.txt'
            if image.exists():
                elements.append(row([column(intro, vertical_align='center'), column([
                    {'tag':'img', 'img_key':image.read_text().strip(), 'alt':txt('餐桌氛围插图'),
                     'scale_type':'crop_center', 'size':'80px 80px', 'corner_radius':'12px', 'preview':False}
                ], width='80px')]))
            else:
                elements.append(panel(intro))
            elements.append(primary('帮我们挑一道', 'draw') if choices else button('调整偏好，重新选择', 'settings', kind='default'))
        info = f'{len(choices)} 道可选 · ' + ('来自收藏夹' if pool == 'favorites' else '来自 50 道菜单')
        if excluded:
            info += '\n已避开：' + excluded
        elements.append(muted(info))
        elements.append(actions(button('收藏夹 · ' + str(len(favorites)), 'favorites'),
                                button('最近选择', 'recent', icon='time_outlined')))
    if notice:
        elements.append(muted(notice))
    return shell(('已决定 · ' if confirmed else '吃饭小抽签 · ') + (result['name'] if result else '点一下，决定下一顿'), elements)


def cli(*args):
    process = subprocess.run([CLI, *args], capture_output=True, text=True, timeout=45, cwd=ROOT)
    try:
        response = json.loads(process.stdout or process.stderr)
    except (ValueError, TypeError):
        raise RuntimeError('Feishu request failed') from None
    if process.returncode or not response.get('ok'):
        raise RuntimeError('Feishu request failed: ' + str(response.get('error', {}).get('code', 'unknown')))
    return response.get('data', {})


@contextmanager
def db():
    connection = sqlite3.connect(ROOT / 'meal_card.sqlite', timeout=15)
    connection.row_factory = sqlite3.Row
    connection.executescript('''
      CREATE TABLE IF NOT EXISTS cards (message_id TEXT PRIMARY KEY, result TEXT);
      CREATE TABLE IF NOT EXISTS prefs (chat_id TEXT PRIMARY KEY, excluded TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS favorites (chat_id TEXT, dish_name TEXT, PRIMARY KEY(chat_id,dish_name));
      CREATE TABLE IF NOT EXISTS meal_options (chat_id TEXT PRIMARY KEY, pool TEXT NOT NULL DEFAULT 'all');
      CREATE TABLE IF NOT EXISTS decisions (message_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, dish TEXT NOT NULL, day TEXT NOT NULL, meal TEXT NOT NULL, decided_at TEXT NOT NULL);
    ''')
    columns = {r['name'] for r in connection.execute('PRAGMA table_info(cards)')}
    if 'meta_json' not in columns:
        connection.execute("ALTER TABLE cards ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'")
    connection.commit()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def current(connection):
    pref = connection.execute('SELECT excluded FROM prefs WHERE chat_id=?', (CHAT,)).fetchone()
    pool = connection.execute('SELECT pool FROM meal_options WHERE chat_id=?', (CHAT,)).fetchone()
    favorites = [r['dish_name'] for r in connection.execute('SELECT dish_name FROM favorites WHERE chat_id=?', (CHAT,))]
    recent = [{'dish':json.loads(r['dish']), 'day':r['day'], 'meal':r['meal']}
              for r in connection.execute('SELECT * FROM decisions WHERE chat_id=? ORDER BY decided_at DESC LIMIT 5', (CHAT,))]
    return {'excluded': pref['excluded'] if pref else '', 'pool':pool['pool'] if pool else 'all',
            'favorites':favorites, 'recent':recent}


def send(meal=None):
    require_config()
    now = datetime.datetime.now(TZ)
    meta = {'day':now.date().isoformat(), 'meal':meal or ('dinner' if now.hour >= 15 else 'lunch')}
    with db() as connection:
        options = current(connection)
    data = cli('im', '+messages-send', '--chat-id', CHAT, '--msg-type', 'interactive',
               '--content', json.dumps(card(meta=meta, **options), ensure_ascii=False), '--as', 'bot')
    with db() as connection:
        connection.execute('INSERT OR IGNORE INTO cards(message_id,result,meta_json) VALUES (?,?,?)',
                           (data['message_id'], None, json.dumps(meta)))
    print('card sent', data['message_id'], flush=True)


def decode(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def handle(event):
    if (event.get('chat_id') != CHAT or event.get('operator_id') not in MEMBERS
            or not event.get('card_content') or not event.get('event_id') or not event.get('token')):
        return
    with db() as connection:
        # Serialize transitions and write only after Feishu accepts the new card.
        connection.execute('BEGIN IMMEDIATE')
        record = connection.execute('SELECT * FROM cards WHERE message_id=?', (event.get('message_id'),)).fetchone()
        if record is None or connection.execute('SELECT 1 FROM events WHERE event_id=?', (event['event_id'],)).fetchone():
            return
        result = json.loads(record['result']) if record['result'] else None
        meta = decode(record['meta_json'])
        options = current(connection)
        action = decode(event.get('action_value'))
        form = decode(event.get('form_value'))
        is_form = event.get('action_name') == 'save_meal_settings' and 'excluded' in form
        if not is_form and action.get('app') != APP:
            return
        command = 'save' if is_form else action.get('action')
        view, notice = 'home', ''
        confirmed = bool(connection.execute('SELECT 1 FROM decisions WHERE message_id=?', (event['message_id'],)).fetchone())
        if command in ('confirm', 'favorite') and action.get('expected_dish') != (result or {}).get('name'):
            notice = '卡片刚刚更新了，请看一下当前菜品，再做选择。'
        elif command == 'save':
            excluded = '、'.join(words(str(form['excluded'])[:300]))
            pool = form.get('pool', options['pool'])
            if pool not in ('all', 'favorites'):
                pool = 'all'
            connection.execute('INSERT INTO prefs VALUES (?,?) ON CONFLICT(chat_id) DO UPDATE SET excluded=excluded.excluded', (CHAT, excluded))
            connection.execute('INSERT INTO meal_options VALUES (?,?) ON CONFLICT(chat_id) DO UPDATE SET pool=excluded.pool', (CHAT, pool))
            options = current(connection)
            if result and not confirmed and result['name'] not in {d['name'] for d in eligible(excluded, pool, options['favorites'])}:
                result = None
                confirmed = False
                connection.execute('DELETE FROM decisions WHERE message_id=?', (event['message_id'],))
            notice = '偏好已保存，下一次抽签立即生效。'
        elif command in ('settings', 'favorites', 'recent'):
            view = command
            try:
                meta['page'] = max(0, min(9, int(action.get('page', 0))))
            except (TypeError, ValueError):
                meta['page'] = 0
        elif command == 'back':
            pass
        elif command == 'use_all':
            connection.execute("INSERT INTO meal_options VALUES (?,'all') ON CONFLICT(chat_id) DO UPDATE SET pool='all'", (CHAT,))
            options['pool'] = 'all'
            notice = '已切换到全部菜单。'
        elif command in ('draw', 'choose'):
            choices = eligible(options['excluded'], options['pool'], options['favorites'])
            if command == 'choose':
                # Manual selection from history/favorites still honors dietary exclusions.
                choices = [d for d in eligible(options['excluded']) if d['name'] == action.get('dish')]
            if not choices:
                view = 'settings'
                notice = '没有符合当前偏好的菜。可以减少忌口，或从全部菜单抽。'
            else:
                recent_names = [r['dish']['name'] for r in options['recent'][:3]]
                seen = meta.get('seen', [])[-4:]
                unique = [d for d in choices if d['name'] not in seen + recent_names]
                different = [d for d in choices if not result or d['name'] != result['name']]
                result = random.SystemRandom().choice(unique or different or choices)
                meta['seen'] = (seen + [result['name']])[-4:]
                confirmed = False
                connection.execute('DELETE FROM decisions WHERE message_id=?', (event['message_id'],))
        elif command == 'confirm':
            if not result:
                notice = '先抽一道喜欢的菜，再确认这一餐。'
            elif result['name'] not in {d['name'] for d in eligible(options['excluded'])}:
                view = 'settings'
                notice = '共享忌口已经更新，这道菜不再符合偏好，请重新选择。'
            else:
                now = datetime.datetime.now(TZ)
                connection.execute('''INSERT INTO decisions VALUES (?,?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET
                    dish=excluded.dish,day=excluded.day,meal=excluded.meal,decided_at=excluded.decided_at''',
                    (event['message_id'], CHAT, json.dumps(result, ensure_ascii=False), meta.get('day', now.date().isoformat()),
                     meta.get('meal', ''), now.isoformat()))
                confirmed = True
                notice = '这一餐定好了，已记入最近选择。'
        elif command == 'favorite':
            if result:
                if result['name'] in options['favorites']:
                    connection.execute('DELETE FROM favorites WHERE chat_id=? AND dish_name=?', (CHAT, result['name']))
                    notice = '已移出收藏。'
                else:
                    connection.execute('INSERT OR IGNORE INTO favorites VALUES (?,?)', (CHAT, result['name']))
                    notice = '已收藏，下次可以从收藏夹直接选。'
        else:
            return
        options = current(connection)
        updated = card(result, view=view, notice=notice, confirmed=confirmed, meta=meta, **options)
        cli('api', 'POST', '/open-apis/interactive/v1/card/update', '--data',
            json.dumps({'token': event['token'], 'card': updated}, ensure_ascii=False), '--as', 'bot')
        connection.execute('UPDATE cards SET result=?, meta_json=? WHERE message_id=?',
                           (json.dumps(result, ensure_ascii=False) if result else None, json.dumps(meta), event['message_id']))
        connection.execute('INSERT INTO events VALUES (?)', (event['event_id'],))
        print('card updated', command, flush=True)


def require_config():
    if not CHAT or not MEMBERS:
        raise RuntimeError('Configure chat_id and member_ids in config.json first')


def listen():
    require_config()
    while True:
        process = subprocess.Popen([CLI, 'event', 'consume', 'card.action.trigger', '--as', 'bot', '--timeout', '6h',
                                    '--jq', 'select(.chat_id == "' + CHAT + '")'],
                                   stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True, cwd=ROOT, start_new_session=True)
        def stop(signum, frame):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        for line in process.stdout:
            try:
                handle(json.loads(line))
            except Exception as error:
                print('callback error', type(error).__name__, str(error)[:100] if isinstance(error, RuntimeError) else '', flush=True)
        code = process.wait()
        if code:
            raise SystemExit(code)


if __name__ == '__main__':
    if sys.argv[1] == 'preview':
        print(json.dumps(card(), ensure_ascii=False, indent=2))
    elif sys.argv[1] == 'send':
        send()
    elif sys.argv[1] == 'listen':
        listen()
