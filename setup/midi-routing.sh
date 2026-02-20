#!/bin/bash
# Waits for the Mac's Network MIDI session to appear, then routes
# bidirectionally between it and the C2MIDI Pro USB controller.
# Installed to /usr/local/bin/midi-routing.sh and run by midi-routing.service.

for i in $(seq 1 30); do
    if aconnect -l | grep -q "MacBook Air"; then
        aconnect "C2MIDI Pro MIDI 1" "Bryan's MacBook Air"
        aconnect "Bryan's MacBook Air" "C2MIDI Pro MIDI 1"
        echo "MIDI routing established: C2MIDI Pro <-> Bryan's MacBook Air"
        exit 0
    fi
    sleep 2
done

echo "Timed out waiting for MacBook Air Network MIDI connection"
exit 1
