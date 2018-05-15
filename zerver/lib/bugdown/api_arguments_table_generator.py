import re
import os
import ujson

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from zerver.lib.openapi import get_openapi_parameters
from typing import Any, Dict, Optional, List
import markdown

REGEXP = re.compile(r'\{generate_api_arguments_table\|\s*(.+?)\s*\|\s*(.+)\s*\}')


class MarkdownArgumentsTableGenerator(Extension):
    def __init__(self, configs: Optional[Dict[str, Any]]=None) -> None:
        if configs is None:
            configs = {}
        self.config = {
            'base_path': ['.', 'Default location from which to evaluate relative paths for the JSON files.'],
        }
        for key, value in configs.items():
            self.setConfig(key, value)

    def extendMarkdown(self, md: markdown.Markdown, md_globals: Dict[str, Any]) -> None:
        md.preprocessors.add(
            'generate_api_arguments', APIArgumentsTablePreprocessor(md, self.getConfigs()), '_begin'
        )


class APIArgumentsTablePreprocessor(Preprocessor):
    def __init__(self, md: markdown.Markdown, config: Dict[str, Any]) -> None:
        super(APIArgumentsTablePreprocessor, self).__init__(md)
        self.base_path = config['base_path']

    def run(self, lines: List[str]) -> List[str]:
        done = False
        while not done:
            for line in lines:
                loc = lines.index(line)
                match = REGEXP.search(line)

                if match:
                    filename = match.group(1)
                    doc_name = match.group(2)
                    filename = os.path.expanduser(filename)

                    is_openapi_format = filename.endswith('.yaml')

                    if not os.path.isabs(filename):
                        parent_dir = self.base_path
                        filename = os.path.normpath(os.path.join(parent_dir, filename))

                    try:
                        if is_openapi_format:
                            endpoint, method = doc_name.rsplit(':', 1)
                            arguments = get_openapi_parameters(endpoint, method)
                        else:
                            with open(filename, 'r') as fp:
                                json_obj = ujson.load(fp)
                                arguments = json_obj[doc_name]

                        text = self.render_table(arguments)
                    except Exception as e:
                        print('Warning: could not find file {}. Ignoring '
                              'statement. Error: {}'.format(filename, e))
                        # If the file cannot be opened, just substitute an empty line
                        # in place of the macro include line
                        lines[loc] = REGEXP.sub('', line)
                        break

                    # The line that contains the directive to include the macro
                    # may be preceded or followed by text or tags, in that case
                    # we need to make sure that any preceding or following text
                    # stays the same.
                    line_split = REGEXP.split(line, maxsplit=0)
                    preceding = line_split[0]
                    following = line_split[-1]
                    text = [preceding] + text + [following]
                    lines = lines[:loc] + text + lines[loc+1:]
                    break
            else:
                done = True
        return lines

    def render_table(self, arguments: List[Dict[str, Any]]) -> List[str]:
        table = []
        beginning = """
<table class="table">
  <thead>
    <tr>
      <th>Argument</th>
      <th>Example</th>
      <th>Required</th>
      <th>Description</th>
    </tr>
  </thead>
<tbody>
"""
        tr = """
<tr>
  <td><code>{argument}</code></td>
  <td><code>{example}</code></td>
  <td>{required}</td>
  <td>{description}</td>
</tr>
"""

        table.append(beginning)

        md_engine = markdown.Markdown(extensions=[])

        for argument in arguments:
            oneof = ['`' + item + '`'
                     for item in argument.get('schema', {}).get('enum', [])]
            description = argument['description']
            if oneof:
                description += '\nMust be one of: {}.'.format(', '.join(oneof))
            # TODO: Swagger allows indicating where the argument goes
            # (path, querystring, form data...). A column in the table should
            # be added for this.
            table.append(tr.format(
                argument=argument.get('argument') or argument.get('name'),
                example=argument['example'],
                required='Yes' if argument.get('required') else 'No',
                description=md_engine.convert(description),
            ))

        table.append("</tbody>")
        table.append("</table>")

        return table

def makeExtension(*args: Any, **kwargs: str) -> MarkdownArgumentsTableGenerator:
    return MarkdownArgumentsTableGenerator(kwargs)
