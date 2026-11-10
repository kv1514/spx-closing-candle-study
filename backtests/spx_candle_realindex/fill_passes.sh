#!/bin/sh
# Repeated short passes over the sessions that still lack a 15:50 bar. The endpoint's answer for an old date
# changes over minutes, so several spaced passes of 2 requests recover more than one long pass.
# usage: fill_passes.sh START END PASSES [SYMBOL OUTFOLDER]   (default .SPX cnbc_1m, which is frozen)
cd /Users/kv15/trading || exit 1
i=1
while [ "$i" -le "$3" ]; do
  out=$(.venv/bin/python -B backtests/spx_candle_realindex/fetch_cnbc.py --start "$1" --end "$2" --fill 2 --gap 0.5 --symbol "${4:-.SPX}" --out "${5:-cnbc_1m}" | tail -1)
  echo "pass $i ($1..$2): $out"
  case "$out" in *"filled 0 "*|*"needed 0 "*) break;; esac
  i=$((i + 1))
done
