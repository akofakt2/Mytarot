import os
import sys

# Pridaj aktuálny adresár do cesty
sys.path.insert(0, os.path.dirname(__file__))

# Aktivuj venv (ak ho máš v priečinku 'venv')
venv_path = os.path.join(os.path.dirname(__file__), 'venv/bin/python3')
if sys.executable != venv_path:
    os.execl(venv_path, venv_path, *sys.argv)

from tarot_app import create_tarot_app 

application = create_tarot_app()