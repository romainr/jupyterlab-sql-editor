import re
from html import escape

import trino
from IPython.core.display import HTML
from IPython.core.magic import Magics, line_cell_magic, line_magic, cell_magic, magics_class, needs_local_scope
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from traitlets import Int, Unicode, Instance
from .schema_export import checkAndUpdateSchema

BIND_VARIABLE_PATTERN = re.compile(r'{([A-Za-z0-9_]+)}')

DEFAULT_SCHEMA_OUTFILE = '/tmp/trinodb.schema.json'
DEFAULT_SCHEMA_TTL = 3600
DEFAULT_CATALOGS = 'default'

@magics_class
class TrinoSql(Magics):
    limit = Int(20, config=True, help='The maximum number of rows to display')
    outputFile = Unicode(DEFAULT_SCHEMA_OUTFILE, config=True, help=f'Output schema to specified file, defaults to {DEFAULT_SCHEMA_OUTFILE}')
    cacheTTL = Int(DEFAULT_SCHEMA_TTL, config=True, help=f'Re-generate output schema file if older than time specified (defaults to {DEFAULT_SCHEMA_TTL} seconds)')
    catalogs = Unicode(DEFAULT_CATALOGS, config=True, help=f'Retrive schema from the specified list of catalogs (defaults to "{DEFAULT_CATALOGS}")')

    host = Unicode('localhost', config=True, help='The trino server hostname)')
    port = Int(443, config=True, help='Trino server port number)')
    httpScheme = Unicode('https', config=True, help='Trino server scheme https/http)')
    auth = Instance(klass='trino.auth.Authentication', config=True, help='An instance of the Trino Authentication class')    

    @needs_local_scope
    @line_cell_magic
    @magic_arguments()
    @argument('sql', nargs='*', type=str, help='SQL statement')
    @argument('-l', '--limit', type=int, help='The maximum number of rows to display')
    @argument('-f', '--outputFile', type=str, help=f'Output schema to specified file, defaults to {DEFAULT_SCHEMA_OUTFILE}')
    @argument('-t', '--cacheTTL', type=int, help=f'Re-generate output schema file if older than time specified (defaults to {DEFAULT_SCHEMA_TTL} seconds)')
    @argument('-a', '--catalogs', type=str, help='Retrive schema from the specified list of catalogs')
    def trinosql(self, line=None, cell=None, local_ns=None):
        "Magic that works both as %trinosql and as %%trinosql"

        if local_ns is None:
            local_ns = {}

        user_ns = self.shell.user_ns.copy()
        user_ns.update(local_ns)

        args = parse_argstring(self.trinosql, line)

        conn = trino.dbapi.connect(
            host=self.host,
            port=self.port,
            auth=self.auth,
            http_scheme=self.httpScheme)
        cur = conn.cursor()

        outputFile = args.outputFile or self.outputFile
        cacheTTL = args.cacheTTL or self.cacheTTL
        catalogs = args.catalogs or self.catalogs
        checkAndUpdateSchema(cur, outputFile, cacheTTL, catalogs.split(','))

        sql = cell
        if cell is None:
            sql = ' '.join(args.sql)

        if not sql:
            print('No sql statement to execute')
            return

        limit = args.limit or self.limit
        sql = bind_variables(sql, user_ns)
        cur.execute(sql)
        rows = cur.fetchmany(limit)
        header = list(map(lambda d: d[0], cur.description))
        
        if len(rows) > limit:
            print('only showing top %d row(s)' % limit)

        html = make_tag('tr',
                        ''.join(map(lambda x: make_tag('td', escape(str(x)), style='font-weight: bold'), header)),
                        style='border-bottom: 1px solid')
        for index, row in enumerate(rows):
            html += make_tag('tr', ''.join(map(lambda x: make_tag('td', escape(str(x))), row)))

        return HTML(make_tag('table', html))


def bind_variables(query, user_ns):
    def fetch_variable(match):
        variable = match.group(1)
        if variable not in user_ns:
            raise NameError('variable `%s` is not defined', variable)
        return str(user_ns[variable])

    return re.sub(BIND_VARIABLE_PATTERN, fetch_variable, query)


def make_tag(tag_name, body='', **kwargs):
    attributes = ' '.join(map(lambda x: '%s="%s"' % x, kwargs.items()))
    if attributes:
        return '<%s %s>%s</%s>' % (tag_name, attributes, body, tag_name)
    else:
        return '<%s>%s</%s>' % (tag_name, body, tag_name)

