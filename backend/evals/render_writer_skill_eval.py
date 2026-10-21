"""Deterministic artifact views/metrics only. No model calls."""
import argparse,json,random,statistics
from pathlib import Path
from backend import publication_rules as pub

def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);args=p.parse_args();folder=Path(args.folder)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));rng=random.Random(20261021)
    blind=[];mapping={};rows=[];comparison=['# Writer 六份成稿对照','固定输入、单次运行；原始稿与核验状态均保留。']
    for case in manifest['cases']:
        cid=case['id'];arms=rng.sample(['before','after'],2);mapping[cid]=dict(zip(['A','B'],arms))
        inp=json.loads((folder/'inputs'/(cid+'.json')).read_text(encoding='utf-8'))
        blind += ['\n## '+cid+' / '+case['platform'], '人群：'+inp['brief']['audience'],'目标：'+inp['brief']['goal'],
            '固定卖点：'+'；'.join(c['direction'] for c in inp['plan']['planning_analysis']['candidates'] if c['id'] in case['selected_point_ids'])]
        for label,arm in zip(['A','B'],arms):
            path=folder/(cid+'_'+arm+'.json')
            if not path.exists():continue
            record=json.loads(path.read_text(encoding='utf-8'));t=record['task'];d=t.get('document')
            blind.append('\n### '+label)
            if not d:
                blind.append('没有成稿')
                rows.append(dict(case=cid,platform=case['platform'],arm=arm,status=t['status'],doc_available=False,errors=record['errors'],seconds=record['seconds'],http_calls=record['http_calls'],total_tokens=record['total_tokens']))
                continue
            blind += [d['title'],d['lead'],*[p['text'] for p in d['paragraphs']],d['cta'],' '.join(d['tags'])]
            plan={s['id']:s for s in (t.get('writer_outline') or {}).get('sections',[])}
            blind += ['内部结构：']+[s.get('reader_question','')+' → '+s.get('reader_progress','') for s in plan.values()]
            facts={f['id'] for f in inp['package']['facts']};images={i['id'] for i in inp['package']['images']}
            refs=[f for para in d['paragraphs'] for f in para['fact_ids']];ims=[para['image_id'] for para in d['paragraphs'] if para['image_id']]
            row=dict(case=cid,platform=case['platform'],arm=arm,status=t['status'],doc_available=True,seconds=record['seconds'],http_calls=record['http_calls'],total_tokens=record['total_tokens'],
                fact_refs=len(refs),valid_fact_refs=sum(f in facts for f in refs),image_refs=len(ims),valid_image_refs=sum(i in images for i in ims),
                paragraphs=len(d['paragraphs']),body_chars=sum(len(p['text']) for p in d['paragraphs']),reader_chars=len(pub.reader_text(d)),generic_notes=pub.generic_notes(pub.reader_text(d)),
                review_completed=bool(t.get('review')),review_passed=(t.get('review') or {}).get('passed'),reviewer_issues=(t.get('review') or {}).get('issues',[]),deterministic_issues=record.get('deterministic_issues',[]),errors=record['errors'],prior_errors=record.get('prior_errors',[]),
                writer_seconds=sum(run['seconds'] for run in t.get('writer_runs',[]) if run['stage'] in ('outline','draft')),writer_total_http_seconds=sum(c.get('elapsed_seconds',0) for c in record['calls'] if c['model']==manifest['models']['writer_model']),repair=bool(t.get('repair_before')),
                stage_seconds=[dict(stage=run['stage'],seconds=run['seconds']) for run in t.get('writer_runs',[])])
            rows.append(row)
            comparison += ['\n## '+cid+' '+arm,'状态：'+t['status'],d['title'],d['lead'],*[p['text'] for p in d['paragraphs']],d['cta'],' '.join(d['tags']),
                '图片ID：'+', '.join(ims),'核验问题：'+json.dumps(row['reviewer_issues'],ensure_ascii=False)]
    for name,data in [('metrics.json',rows),('blind_mapping.json',mapping)]:
        (folder/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'blind_reading.md').write_text('\n\n'.join(blind),encoding='utf-8')
    supplement=folder/'CP11_after_recovery.json'
    if supplement.exists():
        rec=json.loads(supplement.read_text(encoding='utf-8'));t=rec['task'];d=t.get('document')
        comparison += ['\n## CP11 after 补测（首轮结构失败另存，不纳入首轮比较）','状态：'+t['status']]
        if d:comparison += [d['title'],d['lead'],*[p['text'] for p in d['paragraphs']],d['cta'],' '.join(d['tags'])]
        comparison += ['核验：'+json.dumps(t.get('review') or dict(error=rec['errors']),ensure_ascii=False)]
    (folder/'comparison.md').write_text('\n\n'.join(comparison),encoding='utf-8')
    print('Available outputs:',len(rows))
    for r in rows:print(r['case'],r['arm'],r['status'],'paragraphs',r.get('paragraphs'),'chars',r.get('reader_chars'),'writer sec',round(r.get('writer_seconds',0),2),'total sec',round(r['seconds'],2),'review completed',r.get('review_completed',False))
if __name__=='__main__':main()
