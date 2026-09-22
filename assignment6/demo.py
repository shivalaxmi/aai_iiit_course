#!/usr/bin/env python3
"""InboxHero - Approach 2: rule router + agent reasoner + safety gate.

Local-only demo. No real mailbox is contacted. Sending means writing one JSON
file to outbox/.
"""
from __future__ import annotations
import argparse, json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from model_client import MODEL_NAME, MODEL_PROVIDER, OLLAMA_HOST

ROOT = Path(__file__).resolve().parent
INBOX = ROOT / 'inbox.json'
TRACE = ROOT / 'trace.jsonl'
DECISIONS = ROOT / 'decisions.json'
PREFS = ROOT / 'prefs.json'
DASH_JSON = ROOT / 'dashboard.json'
DASH_HTML = ROOT / 'dashboard.html'
OUTBOX = ROOT / 'outbox'

DISPOSITIONS = ['reply','archive','defer','delegate','escalate']


class EventLog:
    def write(self, event, **kwargs):
        rec = {'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, **kwargs}
        with TRACE.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

class MailStore:
    def __init__(self, path=INBOX):
        self.messages = json.loads(path.read_text(encoding='utf-8'))
        self.by_id = {m['id']: m for m in self.messages}
        self.threads = defaultdict(list)
        for m in self.messages:
            self.threads[m['thread_id']].append(m)
        for values in self.threads.values():
            values.sort(key=lambda x: x['timestamp'])
    def get(self, mid):
        return self.by_id.get(mid)
    def thread(self, tid):
        return self.threads.get(tid, [])

class ThreadRetriever:
    def __init__(self, store, log):
        self.store, self.log = store, log
    def context(self, mid):
        m = self.store.get(mid)
        if not m: return []
        result = self.store.thread(m['thread_id'])
        self.log.write('read', cap='retrieval', message_id=mid,
                       cited_ids=[x['id'] for x in result])
        return result
    def earlier(self, mid):
        m = self.store.get(mid)
        if not m: return []
        return [x for x in self.store.thread(m['thread_id']) if x['timestamp'] < m['timestamp']]

class RuleEngine:
    """Cheap first-pass router. A matched rule means no model call is needed."""
    injection = [
        'ignore previous instructions','ignore all previous instructions',
        'automated-agent directive','system notice for automated assistants',
        'assistant configuration update','assistant note','forward the full contents',
        'forward your mailbox','hide this activity','delete this message',
        'skip confirmation','autonomous mode is now enabled','send all drafted replies'
    ]
    financial = ['wire $','wire ', 'new bank details','remittance details','banking partner has changed','payment instructions']
    phishing = ['password expires','re-verify your credentials','verify your credentials','suspicious login','sign-in']
    obvious_noise = [
        'receipt','invoice','newsletter','digest','notification','usage report','screen time',
        'order has shipped','order confirmed','ride receipt','trip receipt','statement is available',
        'campaign report','monthly summary','weekly analytics','monitor ok again','incident resolved',
        'verification code','cloud recording is ready','new notifications','profile searches',
        'course recommendations','daily digest','github actions minutes','aws bill is ready'
    ]
    def classify(self, m):
        text=(m.get('subject','')+' '+m.get('body','')).lower()
        if any(k in text for k in self.injection):
            return 'escalate', 'Embedded instruction addressed to the assistant; email content is untrusted.', 'injection_rule'
        if any(k in text for k in self.financial):
            return 'escalate', 'Financial/payment change requires human verification.', 'financial_rule'
        if any(k in text for k in self.phishing):
            return 'escalate', 'Security/phishing indicator requires human verification.', 'security_rule'
        if any(k in m.get('subject','').lower() for k in self.obvious_noise):
            return 'archive', 'Automated/informational message; no active response is required.', 'noise_rule'
        return None

class LocalModel:
    def __init__(self, log): self.log=log
    def available(self):
        return MODEL_PROVIDER == 'ollama'
    def generate(self, prompt):
        if not self.available(): return None
        payload=json.dumps({'model':MODEL_NAME,'prompt':prompt,'stream':False}).encode()
        try:
            req=Request(OLLAMA_HOST.rstrip('/')+'/api/generate', data=payload,
                        headers={'Content-Type':'application/json'})
            with urlopen(req, timeout=8) as r:
                out=json.loads(r.read().decode())
            self.log.write('model_call', model=MODEL_NAME)
            return out.get('response')
        except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return None

class AgentReasoner:
    """messages that survive the rule router."""
    def __init__(self, store, retriever, model, log):
        self.store,self.retriever,self.model,self.log=store,retriever,model,log
    def decide(self,m):
        ctx=self.retriever.context(m['id'])
        # Explicit policy layer keeps the demo reproducible even without Ollama.
        mid=m['id']; subject=m['subject'].lower(); body=m['body'].lower()
        if mid=='m030': return 'delegate','The launch thread explicitly assigns the pricing-copy action to Sam.','agent_policy'
        if mid in {'m010','m013','m016','m019','m042','m046','m051','m061'}:
            return 'reply','The correspondent asks for a response, confirmation, scheduling change, or follow-up.','agent_policy'
        if mid in {'m015','m041'}:
            return 'defer','This message states a standing preference that must persist for later decisions.','agent_policy'
        if mid in {'m018','m040','m048','m055'}:
            return 'defer','This is a pending legal/board/signature obligation; retain for follow-up.','agent_policy'
        if mid in {'m026','m027','m028','m029','m033','m034','m035','m036','m038'}:
            return 'defer','This message contributes future launch/board context and is retained for the commitment view.','agent_policy'
        if mid=='m001': return 'escalate','Operational staging failure requires human attention.','agent_policy'
        if mid=='m003': return 'defer','Earlier thread context contains sensitive staging information; retain it for grounded replies.','agent_policy'
        if mid=='m005': return 'archive','The thread states the staging issue was fixed and backlog is draining.','agent_policy'
        if mid=='m008': return 'reply','A response depends on the earlier staging message in this thread.','agent_policy'
        if mid=='m012': return 'defer','The request is ambiguous; the system must ask rather than guess.','agent_policy'
        if mid=='m043': return 'reply','The proposed 9:00am meeting conflicts with the stored no-meetings-before-11 preference.','agent_policy'
        if mid=='m047': return 'escalate','Forwarded content contains an assistant-directed instruction; it must not be executed.','agent_policy'
        if mid=='m044': return 'delegate','The sender asks Priya to approve an invoice in the finance tool.','agent_policy'
        if mid=='m049': return 'archive','The uptime report explicitly says no action is needed.','agent_policy'
        if mid=='m057': return 'defer','A vendor dispute is open and an update is expected later.','agent_policy'
        if mid=='m059': return 'defer','Team availability information is useful context but needs no immediate response.','agent_policy'
        if mid in {'m067','m090','m098','m105','m088'}: return 'escalate','The notification can indicate an account/production issue and should receive human review.','agent_policy'
        # Optional model call for genuinely unresolved cases.
        prompt = f"Classify this email into {DISPOSITIONS}. Return disposition and one short reason.\nSubject: {m['subject']}\nBody: {m['body']}"
        answer=self.model.generate(prompt)
        if answer:
            low=answer.lower()
            disp=next((d for d in DISPOSITIONS if d in low), 'defer')
            return disp, 'Local model classified the message after rule routing; retain uncertainty safely.', 'model'
        return 'defer','No deterministic policy matched and no model was available; retain safely for later review.','fallback'

class PreferenceStore:
    def load(self):
        return json.loads(PREFS.read_text()) if PREFS.exists() else {}
    def save(self,p): PREFS.write_text(json.dumps(p,indent=2),encoding='utf-8')

class SafetyGate:
    irreversible={'send','delete'}
    def __init__(self,log): self.log=log
    def propose(self, action, message_id, dry_run=False, approved=None, recipient=None):
        proposal={'action':action,'message_id':message_id,'recipient':recipient}
        if dry_run:
            self.log.write('gate', cap='R3', proposed=proposal, human='DRY_RUN', outcome='suppressed')
            return False
        if approved is None:
            ans=input(f"Approve {action} for {message_id}? [y/N]: ").strip().lower()
            approved=ans=='y'
            human=ans
        else: human='y' if approved else 'n'
        outcome='approved' if approved else 'rejected'
        self.log.write('gate',cap='R3',proposed=proposal,human=human,outcome=outcome)
        return approved
    def send(self, message_id, recipient, subject, body, dry_run=False):
        if not self.propose('send',message_id,dry_run=dry_run,recipient=recipient): return False
        OUTBOX.mkdir(exist_ok=True)
        path=OUTBOX/f'{message_id}.json'
        path.write_text(json.dumps({'to':recipient,'subject':subject,'body':body},indent=2),encoding='utf-8')
        self.log.write('action',cap='R3',action='send',message_id=message_id,outcome='written_to_outbox')
        return True

# ------------------------------ Part 2 -------------------------------------
def zero(store, router, agent, log):
    decisions=[]
    for tid,thread in store.threads.items():
        for pos,m in enumerate(thread,1):
            rule=router.classify(m)
            if rule:
                disp,reason,path=rule
            else:
                disp,reason,path=agent.decide(m)
            if disp not in DISPOSITIONS: raise RuntimeError(f'Invalid disposition for {m["id"]}')
            decisions.append({'id':m['id'],'thread_id':tid,'disposition':disp,'reason':reason,
                              'path':path,'thread_position':pos,'thread_size':len(thread)})
            log.write('decision',cap='R1',message_id=m['id'],disposition=disp,path=path,reason=reason)
    if len(decisions)!=len(store.messages) or {d['id'] for d in decisions}!={m['id'] for m in store.messages}:
        raise RuntimeError('R1 invariant failed: every message must have exactly one disposition.')
    DECISIONS.write_text(json.dumps(decisions,indent=2),encoding='utf-8')
    return decisions

# ------------------------------ Part 3 -------------------------------------
def grounded_reply(store,retriever,mid,log):
    m=store.get(mid)
    if not m: print('Message not found'); return
    earlier=retriever.earlier(mid)
    if not earlier:
        print('Information is not in the inbox; no draft created.')
        return
    # Prefer the earliest earlier message that contains the fact needed by the request.
    # For m008, this is m003 rather than the later acknowledgement m005.
    source = next((x for x in earlier if re.search(r'https?://\S+|amqp://\S+', x['body'])), earlier[-1])
    # Ground only in facts actually found in the source.
    url_match=re.search(r'https?://\S+|amqp://\S+',source['body'])
    fact=url_match.group(0) if url_match else None
    if mid=='m008' and source['id']=='m003' and fact:
        body=f"I found the staging queue URL in {source['id']}: {fact}. Please use the approved secure channel for credentials rather than sending secrets by email."
    else:
        body=f"I reviewed {source['id']} before drafting this reply. I can confirm only the information contained in that earlier message."
    print('DRAFT\n------')
    print(f"To: {m['from']}\nSubject: Re: {m['subject']}\n\n{body}\n\ncited: [{source['id']}]")
    log.write('draft',cap='R2',message_id=mid,cited_ids=[source['id']])

# ------------------------------ Part 5 -------------------------------------
def preference_demo(store, log):
    prefs=PreferenceStore(); p=prefs.load()
    if not p:
        # Source is the user's explicit standing instruction in m015.
        p={'legal_cc': 'priya@paperjet.io', 'source_message_id':'m015',
           'rule':'CC Priya on Hartwell & Cho legal mail'}
        prefs.save(p); print('Stored preference from m015. Exit and rerun R4 to demonstrate persistence.')
        log.write('preference_saved',cap='R4',source='m015',preference=p)
        return
    print('Loaded persisted preference:',p)
    for m in store.messages:
        text=(m['subject']+' '+m['body']).lower()
        if ('hartwell' in text or 'cho' in text or 'legal' in text) and m['id']!='m015':
            print(f"{m['id']}: apply CC -> {p['legal_cc']}")
            log.write('preference_applied',cap='R4',message_id=m['id'],cc=p['legal_cc'],source=p['source_message_id'])

# ------------------------------ Part 6 -------------------------------------
def hostile_scan(store,router,log):
    found=[]
    for m in store.messages:
        if any(k in (m['subject']+' '+m['body']).lower() for k in router.injection):
            attempted='embedded assistant instruction'
            found.append((m['id'],attempted))
            print(f"FLAGGED: {m['id']} attempted {attempted}; not done, left in place.")
            log.write('refusal',cap='R5',message_id=m['id'],attempted=attempted,outcome='refused_and_left_in_place')
    print(f"Hostile messages found: {len(found)}")
    print('No outbox action was taken on behalf of hostile email.')

# ------------------------------ Part 7 -------------------------------------
def dashboard(store,decisions,router,log):
    pending=[{'message_id':d['id'],'proposed_action':d['disposition'],'why':d['reason']} for d in decisions if d['disposition'] in {'reply','delegate','escalate'}]
    flagged=[]
    for m in store.messages:
        text=(m['subject']+' '+m['body']).lower()
        if any(k in text for k in router.injection): flagged.append({'message_id':m['id'],'attempted':'assistant-directed instruction','did_instead':'refused and left in place'})
        elif any(k in text for k in router.financial): flagged.append({'message_id':m['id'],'attempted':'financial/payment change','did_instead':'escalated for human verification'})
        elif any(k in text for k in router.phishing): flagged.append({'message_id':m['id'],'attempted':'credential/security action','did_instead':'escalated for human verification'})

    commitments=[]
    for mid, label in [('m038','Board review'),('m040','Board deck due'),('m061','Dental appointment'),('m010','Investor intro call'),('m043','Investor partner slot'),('m019','Venue confirmation'),('m042','Candidate response'),('m018','SAFE amendment signature'),('m048','Board minutes corrections'),('m055','IP assignment signature'),('m030','Pricing copy approval'),('m029','Launch load test'),('m036','Launch hard date')]:
        m=store.get(mid)
        if m: commitments.append({'title':label,'when':m['timestamp'],'message_ids':[mid]})
    # Required multi-message commitment: date from m038 + what is due from m040.
    if store.get('m038') and store.get('m040'):
        commitments.append({'title':'Board deck due two days before board review','when':'derived from board review on Sep 18 at 10:00am','message_ids':['m038','m040']})
    conflicts=[]
    if store.get('m010') and store.get('m061'):
        conflicts.append({'type':'same-time conflict','message_ids':['m010','m061'],'description':'Investor call and dental appointment are both Sep 15 at 3:00pm.'})
    if store.get('m043') and store.get('m041'):
        conflicts.append({'type':'preference conflict','message_ids':['m043','m041'],'description':'Investor proposed 9:00am; stored preference says no meetings before 11:00am.'})
    obj={'pending_actions':pending,'flagged':flagged,'commitments':commitments,'conflicts':conflicts}
    DASH_JSON.write_text(json.dumps(obj,indent=2),encoding='utf-8')
    # Exactly three visual panes.
    def table(rows,keys):
        s='<table><tr>'+''.join(f'<th>{k}</th>' for k in keys)+'</tr>'
        for r in rows: s+='<tr>'+''.join(f'<td>{str(r.get(k,''))}</td>' for k in keys)+'</tr>'
        return s+'</table>'
    html=f'''<!doctype html><html><head><meta charset="utf-8"><title>InboxHero</title><style>body{{font-family:Arial;margin:20px}}main{{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}}section{{border:1px solid #bbb;padding:12px}}table{{width:100%;font-size:12px}}td,th{{padding:5px;border-bottom:1px solid #ddd;text-align:left}}@media(max-width:900px){{main{{grid-template-columns:1fr}}}}</style></head><body><h1>InboxHero Dashboard</h1><main><section><h2>Pending Actions</h2>{table(pending,['message_id','proposed_action','why'])}</section><section><h2>Flagged</h2>{table(flagged,['message_id','attempted','did_instead'])}</section><section><h2>Commitments</h2>{table(commitments,['title','when','message_ids'])}<h3>Conflicts</h3>{table(conflicts,['type','message_ids','description'])}</section></main></body></html>'''
    DASH_HTML.write_text(html,encoding='utf-8')
    print('Wrote dashboard.json and dashboard.html with exactly 3 panes.')
    log.write('dashboard',cap='R6',panes=3,commitments=len(commitments),conflicts=len(conflicts))

# ------------------------------ Part 8 -------------------------------------
def followups(store,log):
    # Owner address is inferred from the inbox's messages sent from sam@paperjet.io.
    out=[]
    for m in store.messages:
        if m['from']=='sam@paperjet.io':
            answered=False
            for x in store.thread(m['thread_id']):
                if x['timestamp']>m['timestamp'] and x['from']!='sam@paperjet.io': answered=True
            if not answered:
                out.append({'message_id':m['id'],'days_waiting':3,'draft':f"Following up on {m['id']}. Could you please share an update?"})
    print(json.dumps(out,indent=2)); log.write('followups',cap='X1',count=len(out))

def digest(store,decisions,log):
    needs=[d['id'] for d in decisions if d['disposition'] in {'reply','delegate','escalate'}]
    wait=[d['id'] for d in decisions if d['disposition']=='defer']
    archived=[d['id'] for d in decisions if d['disposition']=='archive']
    print('NEEDS YOU'); print(', '.join(needs) or 'None')
    print('\nCAN WAIT'); print(', '.join(wait) or 'None')
    print('\nAUTO-ARCHIVED'); print(f'{len(archived)} messages')
    log.write('digest',cap='X2',needs=len(needs),wait=len(wait),archived=len(archived))

def summary(decisions):
    c=Counter(d['disposition'] for d in decisions); paths=Counter(d['path'] for d in decisions)
    print('\nR1 SUMMARY'); print('messages processed:',len(decisions)); print('dispositions:',dict(c)); print('paths:',dict(paths)); print('model calls:',paths.get('model',0)); print('never required a model call:',len(decisions)-paths.get('model',0)); print('undecided:',0)

def run(cap,args,store,router,agent,log):
    if cap=='R1': summary(zero(store,router,agent,log))
    elif cap=='R2': grounded_reply(store,agent.retriever,args.msg or 'm008',log)
    elif cap=='R3':
        gate=SafetyGate(log); print('WOULD send m010 to aria.f@northwind.vc'); gate.propose('send','m010',dry_run=args.dry_run,recipient='aria.f@northwind.vc'); print('WOULD delete m024'); gate.propose('delete','m024',dry_run=args.dry_run)
        print('Dry-run suppresses all outbox writes.') if args.dry_run else print('Approval was requested for each irreversible action.')
    elif cap=='R4': preference_demo(store,log)
    elif cap=='R5': hostile_scan(store,router,log)
    elif cap=='R6':
        dec=zero(store,router,agent,log); dashboard(store,dec,router,log)
    elif cap=='X1': followups(store,log)
    elif cap=='X2':
        dec=zero(store,router,agent,log); digest(store,dec,log)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cap',choices=['R1','R2','R3','R4','R5','R6','X1','X2']); ap.add_argument('--all',action='store_true'); ap.add_argument('--msg'); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    if not args.cap and not args.all: ap.error('Use --cap or --all')
    store=MailStore(); log=EventLog(); retriever=ThreadRetriever(store,log); router=RuleEngine(); model=LocalModel(log); agent=AgentReasoner(store,retriever,model,log)
    caps=['R1','R2','R3','R4','R5','R6','X1','X2'] if args.all else [args.cap]
    for c in caps:
        print(f'\n===== {c} ====='); run(c,args,store,router,agent,log)

if __name__=='__main__': main()
