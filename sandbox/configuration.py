"""TOML defaults translated into ordinary CLI options, so CLI overrides win."""
import argparse
from pathlib import Path
import sys
import tomllib


class ConfigParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        argv = list(sys.argv[1:] if args is None else args)
        initial = super().parse_args(argv, namespace)
        filename = getattr(initial, 'config', None)
        if not filename:
            return initial
        path = Path(filename).resolve()
        with path.open('rb') as handle:
            document = tomllib.load(handle)
        data = document.get('sandbox', document)
        if not isinstance(data, dict):
            raise ValueError('La configurazione deve essere una tabella TOML.')
        command = initial.command
        sub = next(a for a in self._actions if isinstance(a, argparse._SubParsersAction)).choices[command]
        actions = {a.dest: a for a in sub._actions if a.dest not in ('help', 'config')}
        tokens = []

        def relative(value):
            return str((path.parent / value).absolute())

        for key, value in data.items():
            if key not in actions:
                raise ValueError(f'Opzione sconosciuta nella configurazione: {key}')
            action = actions[key]
            if key == 'source':
                if not initial.source:
                    if not isinstance(value, str):
                        raise ValueError('source deve essere una stringa.')
                    tokens.append(relative(value))
                continue
            option = action.option_strings[0]
            if isinstance(action, argparse.BooleanOptionalAction):
                if type(value) is not bool:
                    raise ValueError(f'{key} deve essere booleano.')
                tokens.append(option if value else '--no-' + option[2:])
                continue
            if isinstance(action, argparse._StoreTrueAction):
                if type(value) is not bool:
                    raise ValueError(f'{key} deve essere booleano.')
                if value:
                    tokens.append(option)
                continue
            many = isinstance(action, argparse._AppendAction)
            if many and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
                raise ValueError(f'{key} deve essere una lista di stringhe.')
            if not many and (not isinstance(value, (str, int)) or isinstance(value, bool)):
                raise ValueError(f'{key} deve essere una stringa o un intero.')
            for item in value if many else [value]:
                if key in ('project_root', 'requirements', 'include', 'runs_dir'):
                    item = relative(str(item))
                elif key == 'mount':
                    origin, separator, target = item.partition('=')
                    if not separator:
                        raise ValueError('mount richiede PERCORSO=DESTINAZIONE.')
                    item = relative(origin) + '=' + target
                tokens.append(option + '=' + str(item))
        # Config options precede explicit options; repeatable options are additive.
        return super().parse_args([argv[0], *tokens, *argv[1:]], namespace)
