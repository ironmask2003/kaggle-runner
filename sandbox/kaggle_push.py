"""Official Kaggle SDK push with useful server errors and nonzero failure exits."""
import argparse
import sys


def http_error_message(exc):
    response = exc.response
    if response is None:
        return str(exc)
    try:
        body = response.json()
        error = body.get('error', body)
        message = error.get('message') if isinstance(error, dict) else error
    except (ValueError, AttributeError):
        message = None
    return f'Kaggle HTTP {response.status_code}: {message or str(exc)}'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-t', '--timeout')
    args = parser.parse_args(argv)
    from requests.exceptions import HTTPError
    try:
        from kaggle import api
        result = api.kernels_push(args.path, timeout=args.timeout)
        if result is None or result.error:
            raise RuntimeError(result.error if result else 'Kaggle non ha restituito una conferma di invio.')
        print(f'Kernel inviato: {result.url}')
        return 0
    except HTTPError as exc:
        print(http_error_message(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
