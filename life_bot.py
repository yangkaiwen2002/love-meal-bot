import json,sys,subprocess,urllib.request,datetime,pathlib,re,os
from zoneinfo import ZoneInfo
from push_ui import morning_card, news_card
ROOT=pathlib.Path(__file__).resolve().parent
cfg=json.loads(pathlib.Path(os.environ.get('LOVE_MEAL_CONFIG', str(ROOT/'config.json'))).expanduser().read_text())
DATA=pathlib.Path(os.environ.get('LOVE_MEAL_DATA_DIR', str(ROOT/'data'))).expanduser()
DATA.mkdir(parents=True,exist_ok=True)
statefile=DATA/'life_bot_state.json'
state=json.loads(statefile.read_text()) if statefile.exists() else {}
now=datetime.datetime.now(ZoneInfo('Asia/Hong_Kong'))
mode=sys.argv[1]
def send(key,body=None,card=None):
    if key in state: return
    payload={'msg_type':'interactive','card':card} if card else {'msg_type':'text','content':{'text':'💗 生活小管家\n\n'+body}}
    req=urllib.request.Request(cfg['webhook'],data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response: result=json.load(response)
    except Exception:
        raise RuntimeError('机器人请求失败；未记录为已发送') from None
    if result.get('code',result.get('StatusCode',-1)) != 0: raise RuntimeError('机器人拒绝消息: '+str(result.get('msg',result.get('StatusMessage'))))
    state[key]=now.isoformat(); statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    print('sent:',key)
def news():
    args=[os.environ.get('LARK_CLI','lark-cli'),'im','+chat-messages-list','--chat-id',cfg['source_chat'],'--order','desc','--page-size','50','--no-reactions','--as','user']
    p=subprocess.run(args,capture_output=True,text=True,timeout=90)
    if p.returncode: raise RuntimeError('无法读取AI日报来源群')
    data=json.loads(p.stdout)
    if not data.get('ok'): raise RuntimeError('读取日报失败')
    for m in data['data']['messages']:
        content=m.get('content','')
        if m.get('deleted') or 'AI 每日精选' not in content: continue
        start=content.find('📊')
        end=content.find('━━━━━━━━',start)
        if start<0: continue
        selected=content[start:end if end>=0 else len(content)].replace('</card>','')
        selected=re.sub(r'\*\*','',selected)
        send('news:'+m['message_id'],card=news_card(selected,str(m.get('create_time','未知'))))
        return
    print('没有找到可同步的日报')
day=now.date().isoformat()
if mode=='initial':
    send('initial','小管家来报到啦 💗\n记得抹药，也记得按时吃饭～\n之后每天 9:00 提醒抹药和早餐，12:00 提醒午餐，18:00 提醒晚餐。AI 日报有更新时在早上同步。')
    news()
elif mode=='morning':
    send(day+':morning',card=morning_card(now.strftime('%m月%d日')))
    news()
elif mode=='lunch':
    import meal_card
    if day+':lunch' not in state:
        meal_card.send(mode); state[day+':lunch']=now.isoformat(); statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
elif mode=='dinner':
    import meal_card
    if day+':dinner' not in state:
        meal_card.send(mode); state[day+':dinner']=now.isoformat(); statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
else: raise SystemExit('unknown mode')
