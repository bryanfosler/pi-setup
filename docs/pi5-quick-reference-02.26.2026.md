# Raspberry Pi 5 Quick Reference
*bryanfoslerpi5 — updated 02.26.2026*

---

## Connect

```bash
# SSH in (key auth, no password prompt)
ssh bfosler@bryanfoslerpi5.local

# If mDNS isn't resolving, use IP
ssh bfosler@<ip-address>

# Find the Pi's IP on your network
ping bryanfoslerpi5.local
```

---

## System Info

```bash
# Who/where am I
whoami                        # current user
hostname                      # device name
uname -a                      # kernel + OS info
cat /etc/os-release           # distro details

# Hardware
vcgencmd measure_temp         # CPU temperature
vcgencmd get_throttled        # throttling flags (0x0 = healthy)
free -h                       # RAM usage
df -h                         # disk usage
lscpu                         # CPU info
lsusb                         # connected USB devices
```

---

## Processes & Resources

```bash
htop                          # interactive process viewer (q to quit)
top                           # basic process viewer
ps aux                        # list all running processes
kill <PID>                    # kill a process by ID
killall <name>                # kill all processes by name
```

---

## Services (systemctl)

```bash
# Status
sudo systemctl status <service>      # check if running + recent logs
sudo systemctl status rtpmidid
sudo systemctl status midi-routing

# Start / Stop / Restart
sudo systemctl start <service>
sudo systemctl stop <service>
sudo systemctl restart <service>

# Enable / Disable at boot
sudo systemctl enable <service>
sudo systemctl disable <service>

# List all active services
sudo systemctl list-units --type=service --state=running
```

---

## Logs

```bash
# Follow live logs for a service
journalctl -u <service> -f

# Last 50 lines
journalctl -u <service> -n 50

# Logs since last boot
journalctl -u <service> -b

# System-wide recent logs
journalctl -n 100 --no-pager
```

---

## File System

```bash
ls -la                        # list files (including hidden)
cd /path/to/dir               # change directory
cd ~                          # go home
cd -                          # go back to previous dir
pwd                           # print current path

cp source dest                # copy file
mv source dest                # move or rename
rm file                       # delete file
rm -r dir                     # delete directory recursively
mkdir dirname                 # make directory

cat file                      # print file contents
less file                     # scroll through file (q to quit)
nano file                     # simple text editor
```

---

## Permissions

```bash
sudo command                  # run as root
sudo su                       # switch to root shell (exit to leave)
chmod +x file                 # make file executable
chown user:group file         # change owner
```

---

## Networking

```bash
ip a                          # show IP addresses and interfaces
ping google.com               # test internet connectivity
ss -tulnp                     # show listening sockets (TCP/UDP)
sudo ss -ulnp | grep 5004     # verify rtpmidid port is open
curl ifconfig.me              # show your public IP
```

---

## Updates & Packages

```bash
sudo apt update               # refresh package list
sudo apt upgrade              # install available updates
sudo apt full-upgrade         # upgrade including kernel/firmware
sudo apt install <pkg>        # install a package
sudo apt remove <pkg>         # remove a package
sudo apt autoremove           # clean up unused packages
dpkg -l | grep <name>         # check if a package is installed
```

---

## Shutdown & Reboot

```bash
sudo reboot                   # reboot the Pi
sudo shutdown -h now          # safe shutdown (power off)
sudo shutdown -r +5           # reboot in 5 minutes
```

---

## MIDI / Project-Specific

```bash
# Check ALSA MIDI connections
aconnect -l

# Manually re-route if auto-routing dropped
aconnect "C2MIDI Pro MIDI 1" "Bryan's MacBook Air"
aconnect "Bryan's MacBook Air" "C2MIDI Pro MIDI 1"

# Verify rtpmidid is listening on UDP 5004/5005
sudo ss -ulnp | grep -E '500[45]'

# Live rtpmidid log (shows ~3-5ms latency when Mac connected)
journalctl -u rtpmidid -f

# Restart both MIDI services
sudo systemctl restart rtpmidid
sudo systemctl restart midi-routing
```

---

## File Locations on Pi

| Path | Purpose |
|------|---------|
| `/usr/local/bin/rtpmidid` | rtpMIDI daemon (built from source) |
| `/usr/local/bin/midi-routing.sh` | ALSA routing script |
| `/etc/systemd/system/rtpmidid.service` | Service config |
| `/etc/systemd/system/midi-routing.service` | Service config |
| `~/rtpmidid/` | Source tree (keep for rebuilds) |

---

## Quick Troubleshooting

| Problem | Check |
|---------|-------|
| Mac can't see Pi in Audio MIDI Setup | `sudo ss -ulnp \| grep 5004` — port must be open |
| MIDI not routing | `aconnect -l` — look for C2MIDI and Mac entries |
| Service won't start | `journalctl -u <service> -n 50` — read the error |
| Pi running hot | `vcgencmd measure_temp` — >80°C is a problem |
| No internet on Pi | `ping 8.8.8.8` then `ping google.com` — rules out DNS vs routing |
