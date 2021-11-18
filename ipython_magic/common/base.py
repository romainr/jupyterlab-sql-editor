from IPython.core.magic import Magics, line_cell_magic, line_magic, cell_magic, magics_class, needs_local_scope
from traitlets import Int, Unicode, Bool
from jinja2 import Template, StrictUndefined
import os.path as path
import time
import math
import IPython


DEFAULT_SCHEMA_TTL = -1
DEFAULT_CATALOGS = ''


VARIABLE_NOT_FOUND_MSG = '''
A Jinja template variable named {{{var_name}}} was located in your SQL statement.

However Jinja was unable to substitute it's value because the variable "{var_name}" was not found in your ipython kernel.

Option 1: If you intended to use a template variable make sure to assign a value to "{var_name}"
'''

HOW_TO_ESCAPE_MSG = '''
Option 2: If you intended to include "{{" in your statement then you'll need to escape this special Jinja variable delimiter.

To have Jinja ignore parts it would otherwise handle as variables or blocks. For example, if, with the default syntax, you want to use {{ as a raw string in a template and not start a variable, you have to use a trick.

The easiest way to output a literal variable delimiter "{{" is by using a variable expression:

{{ '{{' }}

For bigger sections, it makes sense to mark a block raw. For example, to include example Jinja syntax in a template, you can use this snippet:

%%trino --limit 3
{% raw %}
/*
This is a comment which happens to contain a jinja template
variable {{x}} that we want to keep as is.
*/
{% endraw %}

SELECT
    *
FROM
    {{ table_name }}

'''

RAISING_ERROR_MSG = "Raising an error to prevent statement from being executed incorrectly."

class ExplainUndefined(StrictUndefined):
    __slots__ = ()

    def __str__(self) -> str:
        print(VARIABLE_NOT_FOUND_MSG.format(var_name=self._undefined_name))
        print(HOW_TO_ESCAPE_MSG)
        print(RAISING_ERROR_MSG)
        return super().__str__()


@magics_class
class Base(Magics):
    limit = Int(20, config=True, help='The maximum number of rows to display')
    cacheTTL = Int(DEFAULT_SCHEMA_TTL, config=True, help=f'Re-generate output schema file if older than time specified (defaults to {DEFAULT_SCHEMA_TTL} seconds)')
    catalogs = Unicode(DEFAULT_CATALOGS, config=True, help=f'Retrive schema from the specified list of catalogs (defaults to "{DEFAULT_CATALOGS}")')
    interactive = Bool(False, config=True, help=f'Display results in interactive grid')
    outputFile = Unicode('', config=True, help=f'Output schema to specified file')

    def make_tag(self, tag_name, body='', **kwargs):
        attributes = ' '.join(map(lambda x: '%s="%s"' % x, kwargs.items()))
        if attributes:
            return '<%s %s>%s</%s>' % (tag_name, attributes, body, tag_name)
        else:
            return '<%s>%s</%s>' % (tag_name, body, tag_name)

    def bind_variables(self, query, user_ns):
        t = Template(query, undefined=ExplainUndefined)
        ret = t.render(user_ns)
        return ret

    def get_catalog_array(self):
        catalog_array = []
        if ',' in self.catalogs:
            catalog_array = self.catalogs.split(',')
        return catalog_array
    
    def get_sql_statement(self, cell, sqlArgument):
        sql = cell
        if cell is None:
            sql = ' '.join(sqlArgument)
        if not sql:
            print('No sql statement to execute')
        else:
            sql = self.bind_variables(sql, self.user_ns)
        return sql

    def set_user_ns(self, local_ns):
        if local_ns is None:
            local_ns = {}

        self.user_ns = self.shell.user_ns.copy()
        self.user_ns.update(local_ns)

    def shouldUpdateSchema(self, spark, schemaFileName, refresh_threshold, catalogs):
        file_exists = path.isfile(schemaFileName)
        ttl_expired = False
        if file_exists:
            file_time = path.getmtime(schemaFileName)
            current_time = time.time()
            if current_time - file_time > refresh_threshold:
                print(f'TTL {refresh_threshold} seconds expired, re-generating schema file: {schemaFileName}')
                ttl_expired = True
            
        return (not file_exists) or ttl_expired
    
    def render_grid(self, pdf, limit):
        # It's important to import DataGrid inside this magic function
        # If you import it at the top of the file it will interfere with
        # the use of DataGrid in a notebook cell. You get a message
        # Loading widget...
        from ipydatagrid import DataGrid
        # for every order of magnitude in the limit 10, 100, 1000
        # increase view port height by 10, 20, 30 rows
        # and add 3 rows of padding

        # limit -> num_display_rows
        # 1         -> 3 + 0
        # 10        -> 3 + 10
        # 100       -> 3 + 20
        # 1,000     -> 3 + 30
        # 10,000    -> 3 + 40

        num_display_rows = 3 + math.floor((math.log(limit, 10) * 10))
        base_row_size = 20
        layout_height = f"{num_display_rows * base_row_size}px"
        return DataGrid(pdf, base_row_size=base_row_size, selection_mode="row", layout={"height": layout_height})

    def display_sql(self, sql):
        def _jupyterlab_repr_html_(self):
            from pygments import highlight
            from pygments.formatters import HtmlFormatter

            fmt = HtmlFormatter()
            style = "<style>{}\n{}</style>".format(
                fmt.get_style_defs(".output_html"), fmt.get_style_defs(".jp-RenderedHTML")
            )
            return style + highlight(self.data, self._get_lexer(), fmt)

        # Replace _repr_html_ with our own version that adds the 'jp-RenderedHTML' class
        # in addition to 'output_html'.
        IPython.display.Code._repr_html_ = _jupyterlab_repr_html_
        return IPython.display.Code(data=sql, language="mysql")
