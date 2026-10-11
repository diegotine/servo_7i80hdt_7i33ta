"""Versioned application entry point; require all native cyclic modules."""
import importlib
from importlib.machinery import EXTENSION_SUFFIXES
import sys

MODULES = ('servo', 'mesa7i80hdt', 'loopback', 'timing', 'backend')

def native_modules():
    paths = {}
    for name in MODULES:
        module = importlib.import_module(name)
        path = module.__file__
        if not any(path.endswith(suffix) for suffix in EXTENSION_SUFFIXES):
            raise RuntimeError(f'Módulo {name} não compilado; execute iniciar.sh para reconstruir a versão Cython')
        paths[name] = path
    return paths

if __name__ == '__main__':
    try:
        native_modules()
    except (ImportError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    sys.exit(importlib.import_module('backend').main())
