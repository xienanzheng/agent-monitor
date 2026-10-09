import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from monitor.server.app import create_app
from monitor.server.settings import ServerSettings
from monitor.server.logs import JsonlTail
from monitor.server.status import build_status


def settings(tmp_path):
    return ServerSettings(root=tmp_path, logs_dir=tmp_path/'logs', token='test', home=tmp_path/'home', socket_path='/tmp/no-monitor-health.sock')


def test_comment_marker_is_not_a_valid_hook_registration(tmp_path):
    s=settings(tmp_path)
    p=s.home/'.claude/settings.json';p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'description':'monitor.live_hook'}))
    st=build_status(s,'live',JsonlTail(s.logs_dir/'events.jsonl'),JsonlTail(s.logs_dir/'incidents.jsonl'))
    assert st['health']['agents']['claude']['configured'] is False
    assert st['health']['agents']['claude']['observed'] is False


def test_configured_hooks_still_need_an_observed_event(tmp_path):
    from monitor.install import install_hooks, CLAUDE_EVENTS
    s=settings(tmp_path)
    install_hooks(s.home/'.claude/settings.json',f'"{sys.executable}" -I -m monitor.live_hook --agent claude',CLAUDE_EVENTS)
    st=build_status(s,'live',JsonlTail(s.logs_dir/'events.jsonl'),JsonlTail(s.logs_dir/'incidents.jsonl'))
    assert st['health']['agents']['claude']['configured'] is True
    assert st['health']['agents']['claude']['observed'] is False


def test_analysis_deduplicates_updates_and_separates_incomplete(tmp_path):
    s=settings(tmp_path);s.logs_dir.mkdir()
    rows=[{'agent':'codex','session_id':'s','index':0,'ts':100,'scored_ts':100,'final_severity':7,'category':'other','judge_failed':False},
          {'agent':'codex','session_id':'s','index':0,'ts':100,'scored_ts':101,'settled_by':'output_update','final_severity':7,'category':'other','judge_failed':False},
          {'agent':'codex','session_id':'s','index':1,'ts':110,'final_severity':0,'judge_failed':True,'coverage':'unknown_tool'}]
    (s.logs_dir/'replay').mkdir()
    (s.logs_dir/'replay/events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    c=TestClient(create_app(s),base_url='http://127.0.0.1:8765')
    res=c.get('/api/analysis?source=replay')
    assert res.status_code==200
    d=res.json()
    assert (d['actions'],d['flagged'],d['incomplete'],d['unknown_tools'])==(2,1,1,1)
    assert d['window']['hours'] is None and d['source']=='replay'
    assert c.get('/api/analysis').json()['actions']==0
    assert c.get('/api/analysis?source=wrong').status_code==400


def test_session_count_does_not_count_output_updates(tmp_path):
    from monitor.server.logs import summarize_sessions
    r={'agent':'codex','session_id':'s','index':0,'ts':100,'final_severity':1}
    [s]=summarize_sessions([r,{**r,'settled_by':'output_update','output':'ok'}])
    assert s['actions']==1


def test_daemon_responsiveness_requires_a_reply_not_a_listening_socket():
    import socket, tempfile
    from pathlib import Path
    from monitor.server.status import daemon_health
    p=str(Path(tempfile.mkdtemp(dir='/tmp'))/'m.sock')
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(p);sock.listen(1)
    try:
        health=daemon_health(p,timeout=.02)
        assert health['running'] is True and health['responsive'] is False
    finally: sock.close()


def test_registration_requires_monitor_as_executed_module(tmp_path):
    import sys
    from monitor.health import agent_health
    from monitor.install import install_hooks, CLAUDE_EVENTS
    install_hooks(tmp_path/'.claude/settings.json', f'"{sys.executable}" -I -m other monitor.live_hook --agent claude', CLAUDE_EVENTS)
    assert agent_health(tmp_path,'claude',[])['configured'] is False
