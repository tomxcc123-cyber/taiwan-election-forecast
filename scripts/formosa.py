"""Conservative original-questionnaire adapter; no news commentary or cross-tabs."""
import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin, urlparse
from lxml import html

INDEX = 'https://www.my-formosa.com.tw/Topical/formosapollster'
HOSTS = {'www.my-formosa.com.tw', 'my-formosa.com.tw'}
SOURCE = '美麗島電子報／畢肯'
VERSION = 1


def canonical_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password:
        raise ValueError('Not a Formosa original report')
    return 'https://my-formosa.com.tw'+p.path


def discover(raw):
    doc = html.fromstring(raw.decode('utf-8'))
    entries = {}
    for a in doc.xpath('//a[@href]'):
        title = ''.join(a.text_content().split())
        if not title.startswith('美麗島民調：2026') or not re.search('市長|縣長', title):
            continue
        url = canonical_url(urljoin(INDEX, a.get('href')))
        if re.fullmatch(r'/DOC_\d+\.htm', urlparse(url).path):
            entries[url] = {'url':url,'title':title}
    if not entries:
        raise ValueError('No recognized original county election reports in index')
    return list(entries.values())[:20]


def record(entry, county, start, end, sample, number, candidates, undecided, nonvote, multiple, method, now):
    if not date(2025,1,1) <= date.fromisoformat(start) <= date.fromisoformat(end) <= now:
        raise ValueError('Invalid/future fieldwork')
    values = [c['support'] for c in candidates]+[undecided, nonvote]
    if not 100 <= sample <= 100000 or len(candidates)<2 or any(not 0<=v<=100 for v in values) or abs(sum(values)-100)>.5:
        raise ValueError('Invalid questionnaire counts/percentages')
    url = canonical_url(entry['url'])
    identity = '|'.join([url,end,str(number),','.join(sorted(c['name'] for c in candidates))])
    return {'id':hashlib.sha256(identity.encode()).hexdigest()[:24], 'county':county,
        'source':SOURCE,'pollster_id':'formosa-bic','publisher':'美麗島電子報','source_url':url,
        'report_title':entry['title'],'field_start':start,'date':end,'sample_n':sample,
        'population':'設籍於該縣市、年滿20歲民眾','method':method,
        'margin_of_error':3.0,'confidence_level':95,'funding':'美麗島電子報',
        'supervisor':'戴立安（問卷設計與分析）','population_size':None,
        'sample_note':'加權全體樣本百分比；不投票／廢票與未表態分開保存',
        'question_number':number,'candidates':candidates,'undecided':undecided,'nonvote':nonvote,
        'multiple_matchups':multiple}


def parse(raw, entry, now):
    doc = html.fromstring(raw.decode('utf-8'))
    for node in doc.xpath('//script|//style'):
        node.drop_tree()
    text = unicodedata.normalize('NFKC', doc.text_content())
    text = re.sub(r'\s+', '', text).replace('臺','台')
    # This parser supports this disclosed contractor/method only, not future changed pollsters.
    if not all(token in text for token in ['畢肯','戴立安','年滿20歲','95%','±3.0%','電話訪問']):
        raise ValueError('Unsupported or incomplete sampling metadata')
    county = re.search(r'調查範圍:([\u4e00-\u9fff]{2,3}[市縣])',text)
    dates = re.search(r'調查時間:(\d{4})年(\d+)月(\d+)日至(?:(\d+)月)?(\d+)日',text)
    sample = re.search(r'成功完訪([\d,]+)人',text)
    if not all((county,dates,sample)):
        raise ValueError('Missing fieldwork/county/sample metadata')
    year,month,day,endmonth,endday=dates.groups()
    start=date(int(year),int(month),int(day)).isoformat()
    end=date(int(year),int(endmonth or month),int(endday)).isoformat()
    blocks = re.split(r'(?<!\d)(\d+)、',text)
    questions=[]
    for i in range(1,len(blocks),2):
        number,block=int(blocks[i]),blocks[i+1]
        question=block.split('(1)',1)[0]
        if '會投給誰' not in question or not re.search('市長|縣長',question):
            continue
        options=re.findall(r'\(\d+\)([^()%]+?)(\d+(?:\.\d+)?)%',block)
        candidates=[];undecided=None;nonvote=None
        for label,value in options:
            value=float(value)
            if label=='未明確回答':
                if undecided is not None:raise ValueError('Duplicate undecided')
                undecided=value
            elif label=='不投票/投廢票':
                if nonvote is not None:raise ValueError('Duplicate nonvote')
                nonvote=value
            else:
                match=re.fullmatch(r'(國民黨|民進黨|民眾黨|藍白合|無黨籍)([\u4e00-\u9fff]{2,8})',label)
                if not match:raise ValueError('Unsupported ballot category')
                candidates.append({'name':match[2],'support':value,'bloc':{'國民黨':'blue','民進黨':'dpp','民眾黨':'third','藍白合':'blue','無黨籍':'other'}[match[1]]})
        if undecided is None or nonvote is None or len({c['name'] for c in candidates})!=len(candidates):
            raise ValueError('Incomplete/duplicate vote-intention categories')
        questions.append((number,candidates,undecided,nonvote))
    if not questions:raise ValueError('No supported vote-intention question')
    method='CATI；住宅電話與行動電話雙架構' if '住宅電話與行動電話雙架構' in text else 'CATI；住宅電話隨機抽樣'
    return [record(entry,county[1],start,end,int(sample[1].replace(',','')),n,c,u,v,len(questions)>1,method,now)
            for n,c,u,v in questions]
