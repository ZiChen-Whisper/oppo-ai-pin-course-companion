"""Sentence evidence across device-generated summary boundaries."""
import json


def evidence(store, ids):
    known = {r['id']: r for r in store.records()['items']}
    if not ids or any(i not in known for i in ids): raise ValueError('请选择存在的记录')
    sentences, summaries, unavailable = [], [], []
    for identifier in ids:
        item = known[identifier]; raw = item['raw']; count = 0
        if item['kind'] == 'memory':
            for result_index, result in enumerate(raw.get('results', [])):
                summaries.append({'record_id': identifier, 'result_index': result_index, 'title': result.get('title'), 'start': result.get('startTime'), 'end': result.get('endTime')})
                for index, sentence in enumerate(result.get('sentences') or []):
                    if not sentence.get('text'): continue
                    sentences.append({**sentence, 'record_id': identifier, 'result_index': result_index, 'sentence_index': index})
                    count += 1
        else:
            value = raw.get('asrText')
            if isinstance(value, str):
                try: value = json.loads(value)
                except ValueError: pass
            if value:
                # Preserve the actual source shape; do not invent per-sentence times.
                sentences.append({'record_id': identifier, 'text': value, 'startTime': raw.get('startTime'), 'endTime': raw.get('endTime'), 'record_level_time': True})
                count += 1
        if not count: unavailable.append(identifier)
    timed = sorted([s for s in sentences if isinstance(s.get('startTime'), (int,float)) and isinstance(s.get('endTime'), (int,float)) and s['endTime'] >= s['startTime']], key=lambda s: s['startTime'])
    ranges = []
    for s in timed:
        start, end = s['startTime'], s['endTime']
        if ranges and start <= ranges[-1][1]: ranges[-1][1] = max(end, ranges[-1][1])
        else: ranges.append([start, end])
    # Gaps are only evidence to inspect, not proof that recording failed.
    gaps = [{'start': a[1], 'end': b[0], 'duration_ms': b[0]-a[1]} for a,b in zip(ranges, ranges[1:]) if b[0]-a[1] >= 90000]
    return {'record_ids': ids, 'sentences': sentences, 'summary_ranges': summaries,
            'transcript_ranges': ranges, 'gaps_to_check': gaps, 'without_transcript': unavailable,
            'notice': '摘要时间不等于课堂边界；间隔可能是停顿或缺失，需检查相邻记录和原文。未提供时间的原文不补造逐句时间。'}
