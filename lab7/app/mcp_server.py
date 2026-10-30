import os, json, sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from mcp.server.fastmcp import FastMCP
mode=os.environ['SERVER_MODE']
mcp=FastMCP(mode, host='0.0.0.0', port=8000, stateless_http=True)
if mode=='status':
    @mcp.tool()
    def get_service_checks(scenario: str='healthy') -> str:
        """Read service checks from SQLite. scenario: healthy, outage, stale."""
        if scenario not in ('healthy','outage','stale'): raise ValueError('Unknown scenario')
        with sqlite3.connect('/data/checks.db') as db:
            db.execute('CREATE TABLE IF NOT EXISTS checks (scenario TEXT, service TEXT, status TEXT, latency_ms INTEGER, checked_at TEXT)')
            db.execute('DELETE FROM checks WHERE scenario=?',(scenario,))
            stamp=(datetime.now(timezone.utc)-timedelta(minutes=30 if scenario=='stale' else 0)).isoformat()
            rows=[(scenario,s,'down' if scenario=='outage' and s=='shop-postgres' else 'up',450 if scenario=='outage' and s=='shop-postgres' else 25,stamp) for s in ('shop-api','shop-worker','shop-postgres')]
            db.executemany('INSERT INTO checks VALUES (?,?,?,?,?)',rows)
            result=db.execute('SELECT service,status,latency_ms,checked_at FROM checks WHERE scenario=?',(scenario,)).fetchall()
        return json.dumps({'test_data':True,'scenario':scenario,'checks':[dict(zip(('service','status','latency_ms','checked_at'),row)) for row in result]})
else:
    @mcp.tool()
    def get_runbook(service: str) -> str:
        """Read instructions. service must be shop-api, shop-worker or shop-postgres."""
        service={"api":"shop-api","worker":"shop-worker","postgres":"shop-postgres","postgresql":"shop-postgres"}.get(service.lower(),service.lower())
        books=json.loads(Path('/app/runbooks.json').read_text())
        if service not in books: raise ValueError('Unknown service')
        return books[service]
    @mcp.tool()
    def get_oncall_contacts() -> str:
        """Return fictional on-call roles and data freshness policy."""
        return 'Test company ShopTeam: application on-call handles API/worker; database on-call handles PostgreSQL. Checks older than 5 minutes are stale, never evidence of healthy operation.'
    @mcp.tool()
    def save_digest(filename: str, content: str) -> str:
        """Save the final Markdown digest. Filename must end in .md, without directories."""
        if Path(filename).name!=filename or not filename.endswith('.md'): raise ValueError('Invalid filename')
        Path('/reports').mkdir(exist_ok=True)
        p=Path('/reports')/filename
        p.write_text(content)
        return str(p)
mcp.run(transport='streamable-http')
