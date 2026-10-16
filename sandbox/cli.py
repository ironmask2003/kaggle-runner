"""Local orchestration, using the official Kaggle CLI. Local execution is explicit via the local command."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from .bundle import package
from .configuration import ConfigParser
# Conservative decimal-byte budget for the complete kernel source, including base64.
MAX_BYTES = 1_000_000


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    temporary.replace(path)


def kaggle(*args):
    sibling = Path(sys.executable).parent / ('kaggle.exe' if sys.platform == 'win32' else 'kaggle')
    executable = str(sibling) if sibling.is_file() else shutil.which('kaggle')
    if not executable:
        raise RuntimeError('CLI Kaggle assente: attiva il venv e installa requirements.txt.')
    command = ([sys.executable, '-m', 'sandbox.kaggle_push', *map(str, args[2:])]
               if args[:2] == ('kernels', 'push') else [executable, *map(str, args)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=None if args[:2] in (('kernels', 'output'), ('datasets', 'create')) else 180)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Kaggle CLI failed')
    return result.stdout.strip()


def read_run(directory):
    path = Path(directory).resolve()
    return path, json.loads((path / 'run.json').read_text())


def build_package(args):
    return package(args.source, args.include, args.requirements,
                   project_root=args.project_root, mounts=args.mount, excludes=args.exclude,
                   max_bytes=args.max_mib * 1024 * 1024, runs_dir=args.runs_dir)


def execution_config(args, entry, req):
    if args.script_args and Path(entry).suffix == '.ipynb':
        raise ValueError('--arg è supportato solo per script Python.')
    return {'entrypoint': entry, 'python': args.python, 'requirements': req,
            'args': args.script_args, 'cwd': args.cwd}


def local(args):
    from .remote_runner import execute
    if args.gpu or args.accelerator:
        print('local usa le risorse del computer; le preferenze GPU Kaggle non si applicano.')
    if args.dataset or args.competition:
        raise ValueError('local richiede dati locali: usa --mount per collegarli al progetto.')
    payload, entry, req, _ = build_package(args)
    config = execution_config(args, entry, req)
    directory = Path(args.runs_dir).resolve() / ('local-' + uuid.uuid4().hex[:12])
    print(f'Esecuzione locale: {directory}')
    execute(payload, config, directory)
    return directory


def prepare(args):
    if not args.owner or not re.fullmatch(r'[A-Za-z0-9_-]+', args.owner):
        raise ValueError('Username Kaggle non valido.')
    if args.python != 'native' and not args.internet:
        raise ValueError('Python isolato richiede Internet.')
    if (args.requirements or Path(args.source).suffix == '.ipynb') and not args.internet:
        raise ValueError('Requirements e notebook richiedono Internet per installare le dipendenze.')
    if args.accelerator and not args.gpu:
        raise ValueError('--accelerator richiede --gpu.')
    payload, entry, req, hashes = build_package(args)
    config = execution_config(args, entry, req)
    prefix = re.sub(r'[^a-z0-9]+', '-', args.name.lower()).strip('-')[:25] or 'sandbox'
    suffix = datetime.now(timezone.utc).strftime('%y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    slug = prefix + '-' + suffix
    ref = args.owner + '/' + slug
    directory = Path(args.runs_dir).resolve() / slug
    runner = Path(__file__).with_name('remote_runner.py').read_text()
    def render(expression):
        return runner + '\nif __name__ == "__main__":\n    execute(' + expression + ', ' + repr(config) + ')\n'

    inline_expression = repr(base64.b64encode(payload).decode())
    inline_size = len(render(inline_expression).encode('utf-8'))
    transport = args.transport
    if transport == 'auto':
        transport = 'inline' if inline_size < MAX_BYTES else 'dataset'
    if transport == 'inline' and inline_size >= MAX_BYTES:
        raise ValueError(f'Runner di {inline_size} byte: deve restare sotto {MAX_BYTES} byte. Usa --transport dataset o auto.')
    directory.mkdir(parents=True, exist_ok=False)
    dataset_ref = None
    if transport == 'dataset':
        data_dir = directory / 'dataset'
        data_dir.mkdir()
        filename = slug + '.payload'
        (data_dir / filename).write_bytes(payload)
        dataset_ref = args.owner + '/' + slug + '-data'
        write_json(data_dir / 'dataset-metadata.json', {
            'id': dataset_ref, 'title': slug.replace('-', ' ') + ' data',
            'licenses': [{'name': 'other'}]})
        expression = 'load_dataset_payload(' + repr(filename) + ')'
    else:
        expression = inline_expression
    runner = render(expression)
    (directory / 'runner.py').write_text(runner)
    metadata = dict(id=ref, title=slug.replace('-', ' '), code_file='runner.py', language='python',
                    kernel_type='script', is_private=True, enable_gpu=args.gpu,
                    enable_internet=args.internet, dataset_sources=[*args.dataset, *([dataset_ref] if dataset_ref else [])],
                    competition_sources=args.competition, kernel_sources=[], model_sources=[])
    if args.accelerator:
        metadata['machine_shape'] = args.accelerator
    write_json(directory / 'kernel-metadata.json', metadata)
    manifest = {'id': ref, 'url': 'https://www.kaggle.com/code/' + ref, 'state': 'prepared',
                'files_sha256': hashes, 'config': config, 'timeout': args.timeout,
                'transport': transport, 'payload_dataset': dataset_ref,
                'created_utc': datetime.now(timezone.utc).isoformat()}
    write_json(directory / 'run.json', manifest)
    print(f'Preparato: {directory}\nKaggle: {manifest["url"]}\nTrasporto: {transport}; file: {len(hashes)}; archivio: {len(payload) / (1024 * 1024):.2f} MiB\nElenco e hash: {directory / "run.json"}')
    return directory


def submit(directory):
    directory, run = read_run(directory)
    if run['state'] not in ('prepared', 'dataset_uploaded'):
        raise ValueError('Run già inviato o invio incerto. Verifica status; crea un nuovo run per riprovare.')
    if run.get('payload_dataset'):
        if run['state'] == 'prepared':
            # Persist before the network call: an ambiguous upload must not be repeated.
            run['state'] = 'uploading_dataset'
            write_json(directory / 'run.json', run)
            output = kaggle('datasets', 'create', '-p', directory / 'dataset', '--keep-tabular')
            (directory / 'dataset-upload.log').write_text(output)
            run['state'] = 'dataset_uploaded'
            write_json(directory / 'run.json', run)
        wait_dataset(run['payload_dataset'])
    # Only this state means kernel submission has been attempted.
    run['state'] = 'submitting'
    write_json(directory / 'run.json', run)
    try:
        output = kaggle('kernels', 'push', '-p', directory, '-t', run['timeout'])
    except RuntimeError as exc:
        (directory / 'submit-error.log').write_text(str(exc))
        raise
    (directory / 'submit.log').write_text(output)
    run['state'] = 'submitted'
    write_json(directory / 'run.json', run)
    print(output)


def wait_dataset(ref, seconds=600, interval=10):
    deadline = time.monotonic() + seconds
    temporary_errors = 0
    while True:
        try:
            output = kaggle('datasets', 'status', ref)
        except RuntimeError as exc:
            # Newly created private datasets may not yet be visible to this endpoint.
            # Retry only these responses, bounded; persistent permission failures surface.
            if not re.search(r'\b(403|404)\b', str(exc)):
                raise
            temporary_errors += 1
            if temporary_errors > 6 or time.monotonic() >= deadline:
                raise RuntimeError(
                    f'Accesso al dataset non disponibile dopo più tentativi: {ref}. '
                    'Verifica account e permessi. Il caricamento è salvato; '
                    'riprendi con submit sullo stesso run. Dettaglio: ' + str(exc)) from exc
            print(f'Dataset appena caricato non ancora accessibile; nuovo controllo tra {interval}s.')
        else:
            print(output)
            if re.fullmatch(r'ready', output.strip(), re.I):
                return
            if re.search(r'\b(error|failed)\b', output, re.I):
                raise RuntimeError(f'Preparazione dataset fallita: {output}')
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Dataset non pronto: {ref}. Riprendi con submit sullo stesso run.')
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def parse_status(text):
    # CLI versions emit e.g. has status "complete" / KernelWorkerStatus.COMPLETE.
    match = re.search(r'\bstatus\b\s*[:=]?\s*[\"\']?(?:KernelWorkerStatus\.)?(\w+)', text, re.I)
    return match.group(1).lower() if match else 'unknown'


def status(directory):
    directory, run = read_run(directory)
    output = kaggle('kernels', 'status', run['id'])
    current = parse_status(output)
    run['remote_status'] = current
    write_json(directory / 'run.json', run)
    (directory / 'status.log').write_text(output)
    print(output)
    return current


def fetch(directory, logs_only=False):
    directory, run = read_run(directory)
    output_dir = directory / ('logs' if logs_only else 'outputs')
    output_dir.mkdir(exist_ok=True)
    command = ['kernels', 'output', run['id'], '-p', output_dir]
    if logs_only:
        command += ['--file-pattern', r'.*(\.log|result\.json)$']
    print(kaggle(*command))
    print(f'Output locali: {output_dir}')
    return output_dir


def wait(directory, seconds=3600, interval=30):
    deadline = time.monotonic() + seconds
    while True:
        current = status(directory)
        if current == 'complete':
            fetch(directory)
            return 0
        if current in ('error', 'failed', 'cancelled', 'canceled'):
            try:
                fetch(directory, logs_only=True)
            except RuntimeError as exc:
                print(f'Log non ancora disponibili: {exc}', file=sys.stderr)
            return 1
        if current not in ('queued', 'running', 'pending', 'initializing'):
            raise RuntimeError(f'Stato non riconosciuto: {current}. Vedi status.log e pagina Kaggle.')
        if time.monotonic() >= deadline:
            print('Attesa locale scaduta. Il job Kaggle continua; riprendi con wait/status.')
            return 2
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def parser():
    p = ConfigParser(description='Sandbox batch Kaggle per script e notebook Python.')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'run', 'local'):
        q = sub.add_parser(name)
        q.add_argument('source', nargs='?')
        q.add_argument('--config', help='Configurazione TOML riutilizzabile')
        q.add_argument('--project-root', help='Include tutta la cartella preservando i percorsi')
        q.add_argument('--mount', action='append', default=[], help='File/cartella esterna=percorso nel progetto')
        q.add_argument('--exclude', action='append', default=[], help='Glob escluso dalla raccolta')
        q.add_argument('--arg', dest='script_args', action='append', default=[], help='Argomento script; per flag usa --arg=--flag')
        q.add_argument('--cwd', choices=['root', 'entrypoint'], default='root')
        q.add_argument('--max-mib', type=int, default=512)
        q.add_argument('--transport', choices=['auto', 'inline', 'dataset'], default='auto')
        q.add_argument('--owner', help='Username Kaggle, non email')
        q.add_argument('--name', default='sandbox')
        q.add_argument('--python', choices=['native', '3.11', '3.12', '3.13'], default='native')
        q.add_argument('--gpu', action=argparse.BooleanOptionalAction, default=False)
        q.add_argument('--accelerator')
        q.add_argument('--internet', action=argparse.BooleanOptionalAction, default=True)
        q.add_argument('--dataset', action='append', default=[])
        q.add_argument('--competition', action='append', default=[])
        q.add_argument('--include', action='append', default=[], help='File/cartella sotto la radice del progetto; ripetibile')
        q.add_argument('--requirements')
        q.add_argument('--timeout', type=int, default=7200, help='Limite richiesto al job remoto, secondi')
        q.add_argument('--runs-dir', default='runs')
        if name == 'run':
            q.add_argument('--wait', action='store_true')
            q.add_argument('--wait-timeout', type=int, default=10800)
    for name in ('submit', 'status', 'wait', 'fetch', 'logs'):
        q = sub.add_parser(name)
        q.add_argument('run_dir')
        if name == 'wait':
            q.add_argument('--wait-timeout', type=int, default=10800)
            q.add_argument('--interval', type=int, default=30)
    sub.add_parser('doctor')
    return p


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        if args.command in ('prepare', 'run', 'local') and not args.source:
            raise ValueError('Specifica lo script oppure source nel file --config.')
        for key in ('timeout', 'wait_timeout', 'interval', 'max_mib'):
            if hasattr(args, key) and getattr(args, key) <= 0:
                raise ValueError(f'{key} deve essere positivo.')
        if args.command == 'doctor':
            print('Python locale:', sys.version.split()[0])
            print(kaggle('--version'))
            print(kaggle('kernels', 'list', '--mine', '--page-size', '1'))
            print('Autenticazione/lettura API riuscita. GPU e quote si verificano al lancio.')
        elif args.command == 'local':
            local(args)
        elif args.command in ('prepare', 'run'):
            directory = prepare(args)
            if args.command == 'run':
                submit(directory)
                if args.wait:
                    return wait(directory, args.wait_timeout)
        elif args.command == 'submit':
            submit(args.run_dir)
        elif args.command == 'status':
            status(args.run_dir)
        elif args.command == 'wait':
            return wait(args.run_dir, args.wait_timeout, args.interval)
        else:
            fetch(args.run_dir, logs_only=args.command == 'logs')
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'Errore: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nMonitoraggio interrotto; il job remoto continua.', file=sys.stderr)
        return 130
