"""Deterministic project snapshots with explicit external data mappings."""
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import zipfile

SKIP_DIRS = {'__pycache__', 'node_modules', 'venv', 'env', 'runs', 'build', 'dist'}
SECRETS = {'kaggle.json', 'access_token', 'credentials.json', 'credentials', 'id_rsa', 'id_ed25519'}


def package(source, includes=(), requirements=None, *, project_root=None, mounts=(),
            excludes=(), max_bytes=512 * 1024 * 1024, runs_dir=None):
    source = Path(os.path.abspath(source))
    root = Path(os.path.abspath(project_root)) if project_root else source.parent
    if source.suffix not in ('.py', '.ipynb'):
        raise ValueError('Il file deve essere .py oppure .ipynb.')
    files = {}
    total = 0
    blocked = Path(runs_dir).resolve() if runs_dir else None

    def unsafe(path):
        return path.is_symlink() or any(p.is_symlink() for p in path.parents)

    def excluded(rel):
        return any(fnmatch.fnmatchcase(rel, pattern) or
                   any(fnmatch.fnmatchcase(p, pattern) for p in PurePosixPath(rel).parts)
                   for pattern in excludes)

    def add(path, rel, explicit=False):
        nonlocal total
        if unsafe(path):
            raise ValueError(f'Symlink non supportato: {path}')
        if rel == '.' and path.is_dir():
            for child in sorted(path.iterdir()):
                add(child, child.name)
            return
        parts = PurePosixPath(rel).parts
        if not parts or PurePosixPath(rel).is_absolute() or '..' in parts or '\\' in rel:
            raise ValueError(f'Destinazione non valida: {rel}')
        rel = PurePosixPath(rel).as_posix()
        forbidden = (path.name.startswith('.') or path.name in SECRETS or
                     any(p.startswith('.') or p in SECRETS or p.startswith('_sandbox_') for p in parts))
        if forbidden:
            if explicit:
                raise ValueError(f'File nascosto/credenziali/riservato: {path}')
            return
        if excluded(rel) or (blocked and path.resolve().is_relative_to(blocked)):
            return
        if path.is_dir():
            if path.name in SKIP_DIRS or path.name.endswith('.egg-info'):
                return
            for child in sorted(path.iterdir()):
                add(child, (PurePosixPath(rel) / child.name).as_posix())
            return
        if not path.is_file():
            raise ValueError(f'File mancante o non regolare: {path}')
        if path.suffix in ('.pyc', '.pyo', '.pem', '.key'):
            if explicit:
                raise ValueError(f'File escluso: {path}')
            return
        if rel in files:
            if files[rel][0] != path.resolve():
                raise ValueError(f'Due file diversi hanno la stessa destinazione: {rel}')
            return
        total += path.stat().st_size
        if total > max_bytes:
            raise ValueError(f'Payload oltre il limite di {max_bytes // (1024 * 1024)} MiB; usa --max-mib o un dataset Kaggle esistente.')
        data = path.read_bytes()
        if path.suffix == '.ipynb':
            nb = json.loads(data)
            if nb.get('nbformat') != 4 or not isinstance(nb.get('cells'), list):
                raise ValueError('Notebook non valido: richiesto nbformat 4.')
            nb['metadata'] = {k: v for k, v in nb.get('metadata', {}).items() if k in ('kernelspec', 'language_info')}
            for cell in nb['cells']:
                cell['metadata'] = {}
                if cell['cell_type'] == 'code':
                    cell['outputs'] = []
                    cell['execution_count'] = None
            data = json.dumps(nb).encode()
        files[rel] = (path.resolve(), data)

    entry = source.relative_to(root).as_posix()
    add(source, entry, True)
    if project_root:
        if unsafe(root):
            raise ValueError(f'Symlink non supportato: {root}')
        for child in sorted(root.iterdir()):
            add(child, child.name)
    for path in includes:
        path = Path(os.path.abspath(path))
        add(path, path.relative_to(root).as_posix(), True)
    req = None
    if requirements:
        path = Path(os.path.abspath(requirements))
        req = path.relative_to(root).as_posix()
        add(path, req, True)
    for mapping in mounts:
        origin, separator, target = mapping.partition('=')
        if not separator or not origin or not target:
            raise ValueError('--mount richiede PERCORSO=DESTINAZIONE_RELATIVA.')
        add(Path(os.path.abspath(origin)), target, True)
    if entry not in files or (req and req not in files):
        raise ValueError('Entrypoint o requirements esclusi dal pacchetto.')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, (_, content) in sorted(files.items()):
            archive.writestr(name, content)
    return buffer.getvalue(), entry, req, {n: hashlib.sha256(v[1]).hexdigest() for n, v in sorted(files.items())}
