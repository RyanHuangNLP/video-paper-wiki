#!/usr/bin/env bash
# External observer for the CI-139 scale_64 exit-139 report.
# Launches the original pytest command and records wait status, streams,
# rusage, RSS, cgroup, and (when a core is produced) a gdb backtrace.
# It does not edit tests, dependencies, pytest assertions, scale, or CI.
# Exit status is the test process status, except:
#   124  supervisor hit the observation cap and killed the child
#   125  harness setup failed before or while launching the test
set -euo pipefail

usage() {
  cat <<'EOF'
usage: ci_139_repro.sh --checkout DIR --out DIR --mode single|full|self-test-ok|self-test-segv
          [--uv UV_BIN] [--observe-seconds N] [--memory-max BYTES|max]
          [--memory-high BYTES|max] [--label TEXT]
EOF
}

CHECKOUT=""
OUT=""
MODE=""
UV_BIN="${UV_BIN:-uv}"
OBSERVE="3600"
MEM_MAX=""
MEM_HIGH=""
LABEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkout) CHECKOUT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --uv) UV_BIN="$2"; shift 2 ;;
    --observe-seconds) OBSERVE="$2"; shift 2 ;;
    --memory-max) MEM_MAX="$2"; shift 2 ;;
    --memory-high) MEM_HIGH="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 125 ;;
  esac
done

if [[ -z "$CHECKOUT" || -z "$OUT" || -z "$MODE" ]]; then
  usage
  exit 125
fi

mkdir -p "$OUT"
if [[ -e "$OUT/wait_status.json" ]]; then
  echo "refusing to overwrite $OUT/wait_status.json" >&2
  exit 125
fi

export CI139_CHECKOUT="$CHECKOUT"
export CI139_OUT="$OUT"
export CI139_MODE="$MODE"
export CI139_UV="$UV_BIN"
export CI139_OBSERVE="$OBSERVE"
export CI139_MEM_MAX="$MEM_MAX"
export CI139_MEM_HIGH="$MEM_HIGH"
export CI139_LABEL="$LABEL"

exec python3 - <<'PY'
import ctypes, json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

checkout = Path(os.environ["CI139_CHECKOUT"]).resolve()
out = Path(os.environ["CI139_OUT"]).resolve()
mode = os.environ["CI139_MODE"]
uv_bin = os.environ["CI139_UV"]
observe = int(os.environ["CI139_OBSERVE"])
mem_max = os.environ.get("CI139_MEM_MAX") or ""
mem_high = os.environ.get("CI139_MEM_HIGH") or ""
label = os.environ.get("CI139_LABEL") or mode

NODE = "tests/unit/test_flow_status.py::test_scale_64_computed_then_a2_b63_continues_small_scope"

class Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]

class RUsage(ctypes.Structure):
    _fields_ = [
        ("ru_utime", Timeval), ("ru_stime", Timeval),
        ("ru_maxrss", ctypes.c_long), ("ru_ixrss", ctypes.c_long),
        ("ru_idrss", ctypes.c_long), ("ru_isrss", ctypes.c_long),
        ("ru_minflt", ctypes.c_long), ("ru_majflt", ctypes.c_long),
        ("ru_nswap", ctypes.c_long), ("ru_inblock", ctypes.c_long),
        ("ru_oublock", ctypes.c_long), ("ru_msgsnd", ctypes.c_long),
        ("ru_msgrcv", ctypes.c_long), ("ru_nsignals", ctypes.c_long),
        ("ru_nvcsw", ctypes.c_long), ("ru_nivcsw", ctypes.c_long),
    ]

libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.wait4.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.POINTER(RUsage)]
libc.wait4.restype = ctypes.c_int
WNOHANG = 1

def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8", errors="replace")

def run_capture(cmd, path, check=False):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    write_text(path, p.stdout or "")
    if check and p.returncode != 0:
        raise SystemExit(125)
    return p.returncode

def sudo_write(path, data: bytes):
    p = subprocess.run(["sudo", "-n", "tee", path], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"sudo tee {path} failed: {p.stderr.decode()[:400]}")

notes = []
harness_error = None

def fail_setup(msg):
    global harness_error
    harness_error = msg
    write_text(out / "harness_error.txt", msg + "\n")
    payload = {
        "label": label,
        "mode": mode,
        "classification": "harness_error",
        "script_exit": 125,
        "error": msg,
    }
    write_text(out / "wait_status.json", json.dumps(payload, indent=2) + "\n")
    print(msg, file=sys.stderr)
    raise SystemExit(125)

# Short real basetemp. AF_UNIX sun_path is 108 bytes; keep this tiny.
basetemp_root = Path(subprocess.check_output(["mktemp", "-d", "/tmp/c139.XXXXXX"], text=True).strip())
basetemp = basetemp_root / "p"
basetemp.mkdir()
write_text(out / "basetemp_path.txt", str(basetemp) + "\n")

py = checkout / ".venv" / "bin" / "python"
if not py.exists():
    fail_setup(f"missing venv python: {py}")

if mode in {"single", "full"}:
    # Invoke the locked venv interpreter directly. `uv run --offline --no-sync`
    # stays as a parent and reaps the interpreter, so wait4 would see uv's
    # normal exit instead of a signal. The pytest argv matches CI.
    cmd = [str(py), "-m", "pytest",
           "-v", "--tb=short", "--durations=25", "-o", "faulthandler_timeout=300",
           "--basetemp", str(basetemp)]
    if mode == "single":
        cmd.append(NODE)
elif mode == "self-test-ok":
    cmd = [str(py), "-c", "import time; time.sleep(1); raise SystemExit(0)"]
elif mode == "self-test-segv":
    cmd = [str(py), "-c", "import ctypes, time; time.sleep(0.2); ctypes.string_at(0)"]
else:
    fail_setup(f"unknown mode {mode}")

env = os.environ.copy()
# Drop credential-looking values from the recorded env only.
redact_parts = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "KEY", "CREDENTIAL")
recorded_env = {}
for k, v in env.items():
    if any(part in k.upper() for part in redact_parts):
        recorded_env[k] = "<redacted>"
    else:
        recorded_env[k] = v
env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
env["UV_NO_PROGRESS"] = "1"
env["UV_OFFLINE"] = "1"
env["UV_PYTHON_DOWNLOADS"] = "never"
env["PYTHONFAULTHANDLER"] = "1"
env["PYTHONUNBUFFERED"] = "1"
recorded_env.update({
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "UV_NO_PROGRESS": "1",
    "UV_OFFLINE": "1",
    "UV_PYTHON_DOWNLOADS": "never",
    "PYTHONFAULTHANDLER": "1",
    "PYTHONUNBUFFERED": "1",
})
write_text(out / "env.json", json.dumps(recorded_env, indent=2, sort_keys=True) + "\n")
write_text(out / "cmd.txt", " ".join(cmd) + "\n" + json.dumps(cmd) + "\n")
write_text(out / "perturbations.txt",
           "Observation-only settings that are not part of the historical pytest argv:\n"
           "- PYTHONFAULTHANDLER=1 (dump on fatal signals; pytest still owns faulthandler_timeout=300)\n"
           "- PYTHONUNBUFFERED=1 (avoid losing block-buffered stdout on a crash)\n"
           "- parent samples /proc every 2s (RSS, fds, children)\n"
           "- RLIMIT_CORE raised on the child when the hard limit allows, else sudo prlimit\n"
           "- optional memory cgroup applied only when --memory-max/--memory-high is set\n"
           "- /usr/bin/time is not the parent: wait4() on the test pid keeps WIFSIGNALED intact;\n"
           "  rusage is written in time -v field names to time_v.txt\n"
           "- pytest is the venv interpreter, not `uv run`: uv remains a parent and would hide SIGSEGV\n"
           "py-spy is not attached during the run.\n"
           f"uv binary recorded for environment parity: {uv_bin}\n")

run_capture(["bash", "-lc", "ulimit -a"], out / "ulimit.txt")
run_capture(["bash", "-lc", "cat /proc/sys/kernel/core_pattern; echo ---; cat /proc/meminfo; echo ---; nproc; echo ---; uname -a"], out / "host_slice.txt")

cgroup = None
if mem_max or mem_high:
    if not mem_max or not mem_high:
        fail_setup("memory pressure arm requires both --memory-max and --memory-high")
    cgroup = Path(f"/sys/fs/cgroup/ci139d.{os.getpid()}.{time.time_ns()}")
    try:
        subprocess.check_call(["sudo", "-n", "mkdir", "-p", str(cgroup)])
        sudo_write(str(cgroup / "memory.max"), (mem_max + "\n").encode())
        sudo_write(str(cgroup / "memory.high"), (mem_high + "\n").encode())
    except Exception as exc:
        fail_setup(f"cgroup setup failed: {exc}")
    pre = []
    for name in ("memory.max", "memory.high", "memory.current", "memory.peak", "memory.events", "memory.swap.max", "cgroup.controllers"):
        p = cgroup / name
        if p.exists():
            pre.append(f"## {name}\n{p.read_text()}")
    write_text(out / "cgroup_before.txt", "".join(pre))
    write_text(out / "cgroup_path.txt", str(cgroup) + "\n")

stdout_f = open(out / "stdout.log", "wb", buffering=0)
stderr_f = open(out / "stderr.log", "wb", buffering=0)
started = time.time()
write_text(out / "timeline.txt", f"start_epoch {started:.6f}\n")

def preexec():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    except Exception as exc:
        try:
            Path("/tmp").joinpath(f"ci139-rlimit-{os.getpid()}.txt").write_text(repr(exc))
        except Exception:
            pass

proc = subprocess.Popen(
    cmd,
    cwd=str(checkout),
    env=env,
    stdout=stdout_f,
    stderr=stderr_f,
    start_new_session=True,
    preexec_fn=preexec,
)
child = proc.pid
write_text(out / "pid.txt", str(child) + "\n")
# Raise the hard core ceiling if the inherited hard limit is still 0.
pr = subprocess.run(["sudo", "-n", "prlimit", "--core=unlimited:unlimited", f"--pid={child}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
write_text(out / "prlimit_core.txt", pr.stdout or "")
if pr.returncode != 0:
    notes.append("sudo prlimit core failed; core may be unavailable")
if cgroup is not None:
    try:
        sudo_write(str(cgroup / "cgroup.procs"), (str(child) + "\n").encode())
    except Exception as exc:
        # Do not continue a pressure run outside the cgroup.
        try:
            os.killpg(child, signal.SIGKILL)
        except Exception:
            pass
        fail_setup(f"failed to move pid into cgroup: {exc}")

sample_path = out / "sampler.csv"
with sample_path.open("w", encoding="utf-8") as sf:
    sf.write("epoch,elapsed_s,pid,rss_kb,hwm_kb,vsz_kb,threads,fds,utime_ticks,stime_ticks,read_bytes,write_bytes,cg_current,cg_peak,load1,nchildren,child_rss_kb,wchan\n")

def read_status(pid):
    data = {}
    try:
        for line in open(f"/proc/{pid}/status", encoding="utf-8", errors="replace"):
            if ":" in line:
                k, v = line.split(":", 1)
                data[k] = v.strip()
    except OSError:
        return None
    return data

def read_stat_times(pid):
    try:
        raw = open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace").read()
    except OSError:
        return None, None
    rp = raw.rfind(")")
    fields = raw[rp + 2 :].split()
    try:
        return int(fields[11]), int(fields[12])
    except Exception:
        return None, None

def read_io(pid):
    rb = wb = ""
    try:
        for line in open(f"/proc/{pid}/io", encoding="utf-8", errors="replace"):
            if line.startswith("read_bytes:"):
                rb = line.split()[1]
            elif line.startswith("write_bytes:"):
                wb = line.split()[1]
    except OSError:
        pass
    return rb, wb

def descendants(root_pid):
    ppid = {}
    rss = {}
    for ent in os.listdir("/proc"):
        if not ent.isdigit():
            continue
        st = read_status(int(ent))
        if not st:
            continue
        try:
            ppid[int(ent)] = int(st.get("PPid", "0").split()[0])
        except ValueError:
            continue
        vm = st.get("VmRSS", "0")
        try:
            rss[int(ent)] = int(vm.split()[0])
        except ValueError:
            rss[int(ent)] = 0
    kids = []
    stack = [root_pid]
    seen = {root_pid}
    while stack:
        cur = stack.pop()
        for pid, parent in ppid.items():
            if parent == cur and pid not in seen:
                seen.add(pid)
                kids.append(pid)
                stack.append(pid)
    return kids, sum(rss.get(k, 0) for k in kids)

def sample(fh):
    st = read_status(child)
    if not st:
        return
    ut, sti = read_stat_times(child)
    rb, wb = read_io(child)
    kids, krss = descendants(child)
    rss = st.get("VmRSS", "0").split()[0]
    hwm = st.get("VmHWM", "0").split()[0]
    vsz = st.get("VmSize", "0").split()[0]
    threads = st.get("Threads", "")
    try:
        fds = str(len(os.listdir(f"/proc/{child}/fd")))
    except OSError:
        fds = ""
    try:
        load1 = open("/proc/loadavg", encoding="utf-8").read().split()[0]
    except OSError:
        load1 = ""
    wchan = ""
    try:
        wchan = open(f"/proc/{child}/wchan", encoding="utf-8", errors="replace").read().strip()
    except OSError:
        wchan = ""
    cg_c = cg_p = ""
    if cgroup is not None:
        try:
            cg_c = (cgroup / "memory.current").read_text().strip()
            cg_p = (cgroup / "memory.peak").read_text().strip()
        except OSError:
            pass
    now = time.time()
    fh.write(",".join([
        f"{now:.3f}", f"{now - started:.3f}", str(child), rss, hwm, vsz, threads, fds,
        "" if ut is None else str(ut), "" if sti is None else str(sti),
        rb, wb, cg_c, cg_p, load1, str(len(kids)), str(krss), wchan,
    ]) + "\n")
    fh.flush()
    write_text(out / "heartbeat.txt", f"elapsed={now - started:.1f} rss_kb={rss} hwm_kb={hwm} threads={threads} children={len(kids)}\n")

trees = out / "proc_tree.log"
last_tree = 0.0
supervisor = False
status_word = None
ru = RUsage()
next_sample = 0.0
deadline = started + observe

with sample_path.open("a", encoding="utf-8") as sf:
    while True:
        now = time.time()
        if now >= next_sample:
            sample(sf)
            next_sample = now + 2.0
        if now - last_tree >= 30.0:
            tr = subprocess.run(["ps", "-o", "pid,ppid,pgid,stat,nlwp,rss,wchan:20,cmd", "--forest"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with trees.open("a", encoding="utf-8") as tf:
                tf.write(f"\n## t={now - started:.1f}\n")
                # Keep only the test process family plus a short header to limit size.
                lines = (tr.stdout or "").splitlines()
                tf.write("\n".join(lines[:2]) + "\n")
                for line in lines:
                    head = line.strip().split(None, 1)
                    if head and head[0] == str(child):
                        tf.write(line + "\n")
            last_tree = now
        st = ctypes.c_int(0)
        got = libc.wait4(child, ctypes.byref(st), WNOHANG, ctypes.byref(ru))
        if got == child:
            status_word = st.value
            break
        if got < 0:
            err = ctypes.get_errno()
            if err == 10:  # ECHILD
                status_word = None
                notes.append("wait4 ECHILD")
                break
        if time.time() >= deadline:
            supervisor = True
            try:
                os.killpg(child, signal.SIGTERM)
            except OSError as exc:
                notes.append(f"SIGTERM failed: {exc}")
            term_deadline = time.time() + 15
            while time.time() < term_deadline:
                st = ctypes.c_int(0)
                got = libc.wait4(child, ctypes.byref(st), WNOHANG, ctypes.byref(ru))
                if got == child:
                    status_word = st.value
                    break
                time.sleep(0.2)
            else:
                try:
                    os.killpg(child, signal.SIGKILL)
                except OSError as exc:
                    notes.append(f"SIGKILL failed: {exc}")
                st = ctypes.c_int(0)
                got = libc.wait4(child, ctypes.byref(st), 0, ctypes.byref(ru))
                if got == child:
                    status_word = st.value
            break
        time.sleep(0.2)

ended = time.time()
stdout_f.close()
stderr_f.close()
with (out / "timeline.txt").open("a", encoding="utf-8") as tf:
    tf.write(f"end_epoch {ended:.6f}\n")
    tf.write(f"elapsed_s {ended - started:.3f}\n")
    tf.write(f"supervisor_timeout {supervisor}\n")

def decode(status):
    if status is None:
        return {"raw": None}
    if os.WIFEXITED(status):
        return {"raw": status, "kind": "exited", "exit_code": os.WEXITSTATUS(status), "signal": None, "coredump": False}
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        try:
            signal_name = signal.Signals(sig).name
        except ValueError:
            signal_name = str(sig)
        return {
            "raw": status,
            "kind": "signaled",
            "exit_code": None,
            "signal": sig,
            "signal_name": signal_name,
            "coredump": bool(os.WCOREDUMP(status)),
        }
    return {"raw": status, "kind": "other"}

decoded = decode(status_word)
rusage = {
    "user_time_s": ru.ru_utime.tv_sec + ru.ru_utime.tv_usec / 1e6,
    "system_time_s": ru.ru_stime.tv_sec + ru.ru_stime.tv_usec / 1e6,
    "max_rss_kb": ru.ru_maxrss,
    "major_faults": ru.ru_majflt,
    "minor_faults": ru.ru_minflt,
    "voluntary_switches": ru.ru_nvcsw,
    "involuntary_switches": ru.ru_nivcsw,
    "inblock": ru.ru_inblock,
    "oublock": ru.ru_oublock,
    "signals": ru.ru_nsignals,
}
# GNU time -v layout, sourced from wait4 rusage (not a time(1) parent).
time_v = [
    f"User time (seconds): {rusage['user_time_s']:.2f}",
    f"System time (seconds): {rusage['system_time_s']:.2f}",
    f"Maximum resident set size (kbytes): {rusage['max_rss_kb']}",
    f"Major (requiring I/O) page faults: {rusage['major_faults']}",
    f"Minor (reclaiming a frame) page faults: {rusage['minor_faults']}",
    f"Voluntary context switches: {rusage['voluntary_switches']}",
    f"Involuntary context switches: {rusage['involuntary_switches']}",
    f"File system inputs: {rusage['inblock']}",
    f"File system outputs: {rusage['oublock']}",
    f"Signals delivered: {rusage['signals']}",
    "Source: wait4 rusage on the test pid. /usr/bin/time was not interposed because it would report WIFEXITED(128+signal) instead of WIFSIGNALED.",
]
write_text(out / "time_v.txt", "\n".join(time_v) + "\n")

# Cores. Pattern is /tmp/core.%e.%p.%t and may also be core.<pid> in cwd.
cores = []
for pat in [Path("/tmp"), checkout, Path.cwd()]:
    if not pat.is_dir():
        continue
    for cand in pat.glob("core.*"):
        name = cand.name
        if f".{child}." in name or name.endswith(f".{child}") or f".{child}." in (name + "."):
            cores.append(cand)
    direct = pat / f"core.{child}"
    if direct.exists():
        cores.append(direct)
# Also match exact core.%e.%p.%t with this pid.
for cand in Path("/tmp").glob(f"core.*.{child}.*"):
    cores.append(cand)
cores = sorted({c.resolve() for c in cores if c.exists()})
core_dir = out / "cores"
if cores:
    core_dir.mkdir(exist_ok=True)
    moved = []
    for c in cores:
        dest = core_dir / c.name
        try:
            shutil.move(str(c), dest)
            moved.append(str(dest))
        except Exception as exc:
            notes.append(f"core move failed {c}: {exc}")
            moved.append(str(c))
    write_text(out / "cores.txt", "\n".join(moved) + "\n")
else:
    write_text(out / "cores.txt", "no core file matched this pid\n")
    moved = []

gdb = shutil.which("gdb")
if moved and gdb:
    exe = str(py if mode.startswith("self-test") else checkout / ".venv" / "bin" / "python")
    # uv run execs python; the venv interpreter is the right binary.
    for core in moved:
        gdb_out = out / (Path(core).name + ".gdb.txt")
        cmds = [
            "set pagination off",
            "set confirm off",
            "set print thread-events off",
            "echo \\n==== THREADS ====\\n",
            "info threads",
            "echo \\n==== BT ALL ====\\n",
            "thread apply all bt",
            "echo \\n==== REGISTERS ====\\n",
            "info registers",
            "echo \\n==== SIGINFO ====\\n",
            "p $_siginfo",
            "echo \\n==== MAPPINGS ====\\n",
            "info proc mappings",
            "echo \\n==== SHARED ====\\n",
            "info sharedlibrary",
        ]
        argv = [gdb, "-batch", "-n", "-c", core, exe]
        for c in cmds:
            argv.extend(["-ex", c])
        try:
            with gdb_out.open("w", encoding="utf-8", errors="replace") as gf:
                p = subprocess.run(argv, stdout=gf, stderr=subprocess.STDOUT, text=True, timeout=180)
                gf.write(f"\n# gdb exit {p.returncode}\n")
            build = out / (Path(core).name + ".buildids.txt")
            run_capture(["readelf", "-n", exe], build)
            with build.open("a", encoding="utf-8") as bf:
                subprocess.run(["readelf", "-n", core], stdout=bf, stderr=subprocess.STDOUT, text=True)
        except Exception as exc:
            notes.append(f"gdb postmortem failed for {core}: {exc}")
elif moved and not gdb:
    notes.append("gdb not installed; core kept without backtrace")

if cgroup is not None:
    post = []
    for name in ("memory.max", "memory.high", "memory.current", "memory.peak", "memory.events", "memory.stat", "memory.swap.events"):
        pth = cgroup / name
        if pth.exists():
            try:
                post.append(f"## {name}\n{pth.read_text()}\n")
            except OSError as exc:
                post.append(f"## {name}\n<read failed {exc}>\n")
    write_text(out / "cgroup_after.txt", "".join(post))
    # Leave the cgroup only after evidence is on disk.
    leftover = ""
    try:
        leftover = (cgroup / "cgroup.procs").read_text().strip()
    except OSError:
        pass
    if not leftover:
        rm = subprocess.run(["sudo", "-n", "rmdir", str(cgroup)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        notes.append(f"cgroup rmdir rc={rm.returncode} {rm.stdout.strip()[:200]}")
    else:
        notes.append(f"cgroup not removed; procs still present: {leftover}")

oom = subprocess.run(["sudo", "-n", "dmesg", "-T"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
oom_lines = []
for line in (oom.stdout or "").splitlines():
    low = line.lower()
    if "out of memory" in low or "killed process" in low or "oom" in low or str(child) in line:
        oom_lines.append(line)
write_text(out / "dmesg_oom.txt", "\n".join(oom_lines[-200:]) + ("\n" if oom_lines else "no oom/pid lines\n"))

# Node visibility in stdout (full-suite runs).
stdout_text = (out / "stdout.log").read_bytes().decode("utf-8", errors="replace")
node_lines = [ln for ln in stdout_text.splitlines() if NODE in ln]
write_text(out / "node_lines.txt", "\n".join(node_lines) + ("\n" if node_lines else ""))

if supervisor:
    classification = "supervisor_timeout"
    script_exit = 124
elif decoded.get("kind") == "signaled" and decoded.get("signal") == 11:
    classification = "signaled_139"
    script_exit = 139
elif decoded.get("kind") == "signaled":
    classification = "signaled_other"
    script_exit = 128 + int(decoded["signal"])
elif decoded.get("kind") == "exited":
    script_exit = int(decoded["exit_code"])
    classification = "passed" if script_exit == 0 else "exited_nonzero"
else:
    classification = "unknown"
    script_exit = 125

# Keep failed basetemp; drop successful ones.
if script_exit == 0:
    shutil.rmtree(basetemp_root, ignore_errors=True)
    notes.append("basetemp removed after success")
else:
    notes.append(f"basetemp kept at {basetemp}")

payload = {
    "label": label,
    "mode": mode,
    "checkout": str(checkout),
    "pid": child,
    "elapsed_s": round(ended - started, 3),
    "supervisor_timeout": supervisor,
    "classification": classification,
    "script_exit": script_exit,
    "wait": decoded,
    "rusage": rusage,
    "cores": moved,
    "node_lines": node_lines[:20],
    "memory_max": mem_max,
    "memory_high": mem_high,
    "cgroup": str(cgroup) if cgroup else None,
    "notes": notes,
    "cmd": cmd,
}
write_text(out / "wait_status.json", json.dumps(payload, indent=2) + "\n")
print(json.dumps({"classification": classification, "script_exit": script_exit, "elapsed_s": payload["elapsed_s"], "pid": child}))
raise SystemExit(script_exit)
PY
