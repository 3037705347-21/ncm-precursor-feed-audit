#!/usr/bin/env bash
set -euo pipefail

install -m 0644 /solution/measurements.py /workspace/precursor_feed/measurements.py
install -m 0644 /solution/blending.py /workspace/precursor_feed/blending.py
install -m 0644 /solution/charging.py /workspace/precursor_feed/charging.py
install -m 0644 /solution/stoichiometry.py /workspace/precursor_feed/stoichiometry.py
install -m 0644 /solution/conditioning.py /workspace/precursor_feed/conditioning.py
install -m 0644 /solution/crystallization.py /workspace/precursor_feed/crystallization.py
install -m 0644 /solution/washing.py /workspace/precursor_feed/washing.py
install -m 0644 /solution/multistage_washing.py /workspace/precursor_feed/multistage_washing.py
install -m 0644 /solution/validation.py /workspace/precursor_feed/validation.py
