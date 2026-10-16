"""Template executed on Kaggle; payload/config are appended by the local launcher."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import tempfile
import zipfile


def load_dataset_payload(filename, root=Path('/kaggle/input')):
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise ValueError(f'Archivio dataset atteso una sola volta: {filename}; trovati {len(matches)}')
    return matches[0].read_bytes()


def execute(payload, config, working=Path('/kaggle/working')):
    working = Path(working).resolve()
    work = working / 'sandbox_work'
    artifacts = working / 'sandbox_artifacts'
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    start = time.time()
    result = {'status': 'running', 'started_at': start, 'kernel_python': sys.version}
    result_file = artifacts / 'result.json'
    result_file.write_text(json.dumps(result, indent=2))
    log = (artifacts / 'execution.log').open('w', buffering=1)
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['SANDBOX_OUTPUT_DIR'] = str(artifacts.resolve())

    temporary = tempfile.TemporaryDirectory(prefix='kaggle-sandbox-')
    scratch = Path(temporary.name)

    def run(cmd, custom_env=None, cwd=None):
        print('Running:', ' '.join(map(str, cmd)), flush=True)
        with subprocess.Popen([str(x) for x in cmd], cwd=cwd or work, env=custom_env or env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
            for line in proc.stdout:
                print(line, end='', flush=True)
                log.write(line)
            if proc.wait():
                raise RuntimeError(f'Command failed (exit {proc.returncode}); see execution.log')

    try:
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload) if isinstance(payload, str) else payload)) as archive:
            for name in archive.namelist():
                target = (work / name).resolve()
                if not target.is_relative_to(work.resolve()):
                    raise ValueError('Invalid archive path')
            archive.extractall(work)
        python = Path(sys.executable)
        if config['python'] != 'native':
            tools = scratch / 'tools'
            venv = scratch / 'venv'
            run([python, '-m', 'pip', 'install', '--target', tools, 'uv'])
            uv_env = env.copy()
            uv_env['PYTHONPATH'] = str(tools)
            run([python, '-m', 'uv', 'venv', '--python', config['python'], '--seed', venv], uv_env)
            python = venv / 'bin/python'
            env['PATH'] = str(venv / 'bin') + os.pathsep + env.get('PATH', '')
            # Avoid inheriting host Python libraries in the isolated interpreter.
            env.pop('PYTHONPATH', None)
        result['interpreter'] = str(python)
        if config.get('requirements'):
            run([python, '-m', 'pip', 'install', '-r', work / config['requirements']])
        source = work / config['entrypoint']
        cwd = source.parent if config.get('cwd') == 'entrypoint' else work
        env['PYTHONPATH'] = str(work) + os.pathsep + str(work / 'src') + os.pathsep + env.get('PYTHONPATH', '')
        if source.suffix == '.ipynb':
            run([python, '-m', 'pip', 'install', 'nbclient>=0.10,<1', 'nbformat>=5,<6', 'ipykernel>=6,<8'])
            kernel_prefix = scratch / 'kernel'
            run([python, '-m', 'ipykernel', 'install', '--prefix', kernel_prefix, '--name', 'sandbox'])
            env['JUPYTER_PATH'] = str(kernel_prefix / 'share/jupyter') + os.pathsep + env.get('JUPYTER_PATH', '')
            helper = work / '_sandbox_execute_notebook.py'
            helper.write_text('''import sys
from pathlib import Path
import nbformat
from nbclient import NotebookClient
source, output, cwd = map(Path, sys.argv[1:])
nb = nbformat.read(source, as_version=4)
try:
    NotebookClient(nb, timeout=None, kernel_name="sandbox", resources={"metadata": {"path": str(cwd)}}).execute()
finally:
    nbformat.write(nb, output)
''')
            run([python, helper, source, artifacts / 'executed.ipynb', cwd], cwd=cwd)
        else:
            run([python, source, *config.get('args', [])], cwd=cwd)
        result['status'] = 'complete'
    except BaseException as exc:
        result.update(status='error', error=str(exc))
        log.write(traceback.format_exc())
        raise
    finally:
        result['elapsed_seconds'] = round(time.time() - start, 3)
        result_file.write_text(json.dumps(result, indent=2))
        log.close()
        temporary.cleanup()
