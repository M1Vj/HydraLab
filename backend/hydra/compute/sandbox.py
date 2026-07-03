"""SandboxPolicy + LocalSandboxRunner — non-bypassable local execution isolation.

This is the boundary that lets HydraLab run real, user-authored code for the
first time (HL-SAFE-11/12/19). Enforcement is real, not cosmetic:

- CPU limit via ``resource.setrlimit`` in a ``preexec_fn`` (RLIMIT_CPU); memory
  via RLIMIT_AS on Linux (a low address-space cap aborts the interpreter on
  macOS, so memory is best-effort there while wall-clock/CPU/Seatbelt stay hard).
- Wall-clock via a hard timeout that SIGKILLs the child's whole process group
  (``start_new_session=True`` -> ``os.killpg``) so no grandchild survives on POSIX.
- Filesystem + network confinement via macOS's built-in ``sandbox-exec`` or
  Linux ``bwrap`` when available. Hosts without those primitives record
  ``best_effort`` on POSIX, while Windows records ``unconfined`` and requires
  an explicit opt-in before spawning.

Every subprocess is launched with an ARGUMENT VECTOR; ``shell=True`` and shell
string interpolation are never used anywhere in this module.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

try:  # ``resource`` is POSIX-only; guarded so imports never explode on Windows.
    import resource
except ImportError:  # pragma: no cover - non-POSIX host
    resource = None  # type: ignore[assignment]


class SandboxError(RuntimeError):
    """Raised when a run is attempted without a resolvable, safe policy."""


# Environment variables copied into a sandbox child, and only these. os.environ
# is NEVER passed through wholesale (HL-SAFE-19).
DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ")
ENFORCEMENT_SEATBELT = "seatbelt"
ENFORCEMENT_BWRAP = "bwrap"
ENFORCEMENT_BEST_EFFORT = "best_effort"
ENFORCEMENT_UNCONFINED = "unconfined"

# Name tokens/prefixes that mark an env var as a secret. Such a var is dropped
# from the sandbox env even if an allowlist entry would otherwise admit it.
_SECRET_NAME_TOKENS: tuple[str, ...] = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "APIKEY",
    "API_KEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
    "SESSION",
    "AUTH",
)
_SECRET_NAME_PREFIXES: tuple[str, ...] = (
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
    "GOOGLE",
    "AZURE",
    "AWS",
    "HF_",
    "HUGGING",
    "COHERE",
    "MISTRAL",
    "GROQ",
    "HYDRA_PROVIDER",
    "HYDRA_SECRET",
    "HYDRA_HOME",
)


def is_secret_name(name: str) -> bool:
    upper = name.upper()
    if upper.endswith("_KEY") or upper.endswith("_TOKEN"):
        return True
    if any(token in upper for token in _SECRET_NAME_TOKENS):
        return True
    return any(upper.startswith(prefix) for prefix in _SECRET_NAME_PREFIXES)

_BWRAP_USABLE: Optional[bool] = None


def _bwrap_usable() -> bool:
    """True only if ``bwrap`` exists AND can actually create namespaces here.

    A present binary is not enough: containers, hardened kernels, and hosts
    without unprivileged user namespaces have ``bwrap`` on PATH yet fail every
    spawn with "Creating new namespace failed". Probe once (cached) so such
    hosts degrade honestly to ``best_effort`` instead of failing every run.
    """
    global _BWRAP_USABLE
    if _BWRAP_USABLE is not None:
        return _BWRAP_USABLE
    path = shutil.which("bwrap")
    if not path:
        _BWRAP_USABLE = False
        return False
    try:
        probe = subprocess.run(
            [path, "--ro-bind", "/", "/", "--unshare-net", "true"],
            capture_output=True,
            timeout=5,
        )
        _BWRAP_USABLE = probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_USABLE = False
    return _BWRAP_USABLE


def _resolve_enforcement() -> str:
    if sys.platform == "darwin":
        return ENFORCEMENT_SEATBELT if shutil.which("sandbox-exec") else ENFORCEMENT_BEST_EFFORT
    if sys.platform == "win32":
        return ENFORCEMENT_UNCONFINED
    if sys.platform.startswith("linux"):
        return ENFORCEMENT_BWRAP if _bwrap_usable() else ENFORCEMENT_BEST_EFFORT
    return ENFORCEMENT_BEST_EFFORT


@dataclass
class SandboxPolicy:
    """A resolved, per-run isolation policy. Deny-by-default in every dimension."""

    workspace_root: Path
    scratch_dir: Path
    network: str = "none"
    cpu_seconds: int = 5
    memory_bytes: int = 512 * 1024 * 1024
    wall_clock_seconds: int = 10
    log_cap_bytes: int = 1024 * 1024
    env_allowlist: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST
    excluded_secrets: frozenset[str] = field(default_factory=frozenset)
    ignored_paths: tuple[str, ...] = ()
    filesystem_network_enforcement: str = "seatbelt"

    def child_env(self, source_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        """Build the child env from the allowlist only, secrets always excluded."""
        source = os.environ if source_env is None else source_env
        env: dict[str, str] = {
            "HOME": str(self.scratch_dir),
            "TMPDIR": str(self.scratch_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        for name in self.env_allowlist:
            if name in self.excluded_secrets or is_secret_name(name):
                continue
            value = source.get(name)
            if value is not None:
                env[name] = value
        return env


def build_default_policy(
    *,
    workspace_root: Path,
    scratch_dir: Path,
    limits: Optional[dict[str, int]] = None,
    network: str = "none",
    env_allowlist: Optional[Sequence[str]] = None,
    excluded_secrets: Optional[Sequence[str]] = None,
    ignored_paths: Optional[Sequence[str]] = None,
) -> SandboxPolicy:
    """Assemble a deny-default policy from a backend's declared limits.

    Building with no overrides yields: network off, an env restricted to the
    non-secret allowlist, a workspace-confined scratch cwd, and CPU/memory/
    wall-clock ceilings taken from the backend defaults.
    """

    limits = limits or {}
    workspace_root = Path(workspace_root).resolve()
    scratch_dir = Path(scratch_dir).resolve()
    if workspace_root not in scratch_dir.parents and scratch_dir != workspace_root:
        raise SandboxError("scratch dir must live inside the project workspace")
    enforcement = _resolve_enforcement()
    return SandboxPolicy(
        workspace_root=workspace_root,
        scratch_dir=scratch_dir,
        network="none" if network == "none" else network,
        cpu_seconds=int(limits.get("cpu_seconds", 5)),
        memory_bytes=int(limits.get("memory_bytes", 512 * 1024 * 1024)),
        wall_clock_seconds=int(limits.get("wall_clock_seconds", 10)),
        log_cap_bytes=int(limits.get("log_cap_bytes", 1024 * 1024)),
        env_allowlist=tuple(env_allowlist) if env_allowlist is not None else DEFAULT_ENV_ALLOWLIST,
        excluded_secrets=frozenset(excluded_secrets or ()),
        ignored_paths=tuple(ignored_paths or ()),
        filesystem_network_enforcement=enforcement,
    )


def build_seatbelt_profile(policy: SandboxPolicy) -> str:
    """A deny-default Seatbelt profile confined to the scratch dir.

    System paths are readable so the interpreter can exec, but Seatbelt is
    last-match-wins: read of the project workspace *outside* scratch is denied
    and only scratch is re-allowed, so a job that reads or writes any project
    file outside its scratch dir is refused -> ``killed:path_escape``. Write is
    permitted only inside scratch (plus /dev/null). No ``(allow network*)``
    clause is emitted while ``network == "none"``, so outbound network is denied
    by omission -> a connect attempt fails with EPERM -> ``killed:network``.
    """

    scratch = str(policy.scratch_dir)
    workspace = str(policy.workspace_root)
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow signal (target self))",
        "(allow file-read-metadata)",
        "(allow file-read*)",
        # Confine to the workspace: deny reads of project files, then re-allow
        # only the run's scratch dir (which lives inside the workspace).
        f'(deny file-read* (subpath "{workspace}"))',
        f'(allow file-read* (subpath "{scratch}"))',
        f'(allow file-write* (subpath "{scratch}") (literal "/dev/null") (literal "/dev/dtracehelper"))',
    ]
    if policy.network != "none":
        lines.append("(allow network*)")
    return "\n".join(lines) + "\n"


def _preexec(policy: SandboxPolicy):  # pragma: no cover - runs in forked child
    """Set resource ceilings. Session detach is handled by start_new_session."""

    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL(None).prctl(38, 1, 0, 0, 0)
        except Exception:
            pass
    if resource is not None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds))
        except (ValueError, OSError):
            pass
        # RLIMIT_AS is honoured on Linux; on macOS a low address-space cap aborts
        # the interpreter before it runs, so memory is enforced best-effort there
        # (wall-clock + CPU + Seatbelt remain the hard limits).
        if sys.platform != "darwin" and policy.memory_bytes > 0:
            try:
                resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
            except (ValueError, OSError):
                pass


@dataclass
class SandboxResult:
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_s: float
    enforcement: str


class SandboxProcess:
    """A live sandboxed child; poll/terminate for pause-cancel semantics."""

    def __init__(self, popen: subprocess.Popen, *, policy: SandboxPolicy, started: float) -> None:
        self._popen = popen
        self.policy = policy
        self._started = started
        self.pid = popen.pid

    def is_alive(self) -> bool:
        return self._popen.poll() is None

    def _pgid(self) -> Optional[int]:
        if sys.platform == "win32":
            return None
        try:
            return os.getpgid(self._popen.pid)
        except ProcessLookupError:
            return None

    def _kill_group(self) -> None:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(self._popen.pid)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
            try:
                self._popen.kill()
            except OSError:
                pass
            return
        pgid = self._pgid()
        if pgid is None:
            return
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def terminate(self) -> None:
        """Kill the whole process group and remove the scratch dir (no orphans)."""
        self._kill_group()
        try:
            self._popen.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self._kill_group()
        finally:
            shutil.rmtree(self.policy.scratch_dir, ignore_errors=True)

    def wait(self) -> SandboxResult:
        timed_out = False
        try:
            stdout, stderr = self._popen.communicate(timeout=self.policy.wall_clock_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group()
            stdout, stderr = self._popen.communicate()
        duration = time.monotonic() - self._started
        returncode = self._popen.returncode
        status = _classify(policy=self.policy, timed_out=timed_out, returncode=returncode, stderr=stderr or "")
        return SandboxResult(
            status=status,
            exit_code=returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_s=duration,
            enforcement=self.policy.filesystem_network_enforcement,
        )


def _classify(*, policy: SandboxPolicy, timed_out: bool, returncode: Optional[int], stderr: str) -> str:
    if timed_out:
        return "killed:timeout"
    if returncode is not None and returncode < 0:
        sig = -returncode
        if sig == getattr(signal, "SIGXCPU", None):
            return "killed:cpu"
        if sig in (signal.SIGKILL, getattr(signal, "SIGSEGV", -1)):
            return "killed:memory"
    # A clean exit is a success regardless of stderr contents: the sandbox-kill
    # heuristics below scan stderr substrings ("permission denied", "sandbox", …)
    # which legitimately appear in a benign exit-0 job's diagnostic output. Only
    # a non-zero / signalled exit may be classified as a kill.
    if returncode == 0:
        return "succeeded"
    low = stderr.lower()
    if "memoryerror" in low:
        return "killed:memory"
    permission_denied = any(
        marker in low
        for marker in ("operation not permitted", "permission denied", "[errno 1]", "[errno 13]", "sandbox")
    )
    if permission_denied and policy.network == "none" and any(
        token in low for token in ("socket", "connect", "getaddrinfo", "urlopen", "network", "sock")
    ):
        return "killed:network"
    if permission_denied:
        return "killed:path_escape"
    if returncode == 0:
        return "succeeded"
    return "failed"


class LocalSandboxRunner:
    """Launches a job as an argv subprocess under an applied SandboxPolicy.

    A runner constructed without a policy refuses to spawn (HL-SAFE-11): the
    guard is in ``__init__`` so no ``subprocess`` call is ever reached for a
    policy-less run.
    """

    def __init__(self, policy: Optional[SandboxPolicy], *, accept_unconfined: bool = False) -> None:
        if policy is None:
            raise SandboxError("refusing to run: no SandboxPolicy resolved for this job")
        if not isinstance(policy, SandboxPolicy):  # defensive: never trust a duck
            raise SandboxError("invalid SandboxPolicy")
        if policy.filesystem_network_enforcement == ENFORCEMENT_UNCONFINED and not accept_unconfined:
            raise SandboxError("no sandboxing available on this platform; execution requires explicit opt-in")
        self.policy = policy

    def _wrap(self, argv: Sequence[str]) -> list[str]:
        if isinstance(argv, (str, bytes)):
            raise SandboxError("argv must be a list vector, never a shell string")
        argv = list(argv)
        if not argv or not all(isinstance(part, str) for part in argv):
            raise SandboxError("argv must be a non-empty list of strings (never a shell string)")
        if self.policy.filesystem_network_enforcement == ENFORCEMENT_SEATBELT and shutil.which("sandbox-exec"):
            profile = build_seatbelt_profile(self.policy)
            return ["sandbox-exec", "-p", profile, *argv]
        if self.policy.filesystem_network_enforcement == ENFORCEMENT_BWRAP and _bwrap_usable():
            scratch = str(self.policy.scratch_dir)
            wrapped = [
                "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--dev",
                "/dev",
                "--bind",
                scratch,
                scratch,
                "--chdir",
                scratch,
            ]
            if self.policy.network == "none":
                wrapped.append("--unshare-net")
            return [*wrapped, *argv]
        return argv

    def spawn(self, argv: Sequence[str]) -> SandboxProcess:
        wrapped = self._wrap(argv)
        self.policy.scratch_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        popen_kwargs = {
            "cwd": str(self.policy.scratch_dir),
            "env": self.policy.child_env(),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "shell": False,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            popen_kwargs["start_new_session"] = True
            popen_kwargs["preexec_fn"] = lambda: _preexec(self.policy)
        popen = subprocess.Popen(wrapped, **popen_kwargs)  # noqa: S603 - argv vector, shell never used
        return SandboxProcess(popen, policy=self.policy, started=started)

    def run(self, argv: Sequence[str]) -> SandboxResult:
        process = self.spawn(argv)
        result = process.wait()
        shutil.rmtree(self.policy.scratch_dir, ignore_errors=True)
        return result
