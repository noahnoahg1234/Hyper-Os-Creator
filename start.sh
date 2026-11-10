#!/bin/sh
# Start Hyper OS Creator and open it in your browser.
cd "$(dirname "$0")"
exec python3 -m hyperos serve "$@"
