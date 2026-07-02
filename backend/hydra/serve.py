from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from hydra.storage.app_data import app_data_root
from hydra.storage.runtime import BackendRuntime, choose_available_port, choose_bind_host


def serve(project_root: Path | None = None, app_data_root_path: Path | None = None) -> int:
    host = choose_bind_host()
    port = choose_available_port(host=host)
    runtime = BackendRuntime(app_data_root=app_data_root_path or app_data_root(), host=host, port=port)
    acquired = runtime.acquire()
    if not acquired.acquired:
        print(
            f"HydraLab backend is already running (pid {acquired.running_pid}); refusing to start a second writer.",
            file=sys.stderr,
        )
        return 2

    runtime.write_port_file(project_root=project_root)
    os.environ["HYDRALAB_RUNTIME_MANAGED"] = "1"
    os.environ["HYDRALAB_PORT"] = str(port)
    if project_root is not None:
        os.environ["HYDRALAB_PROJECT_ROOT"] = str(project_root)

    try:
        uvicorn.run("hydra.app:app", host=host, port=port, lifespan="on")
    finally:
        runtime.release()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HydraLab local backend.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--app-data-root", type=Path, default=None)
    args = parser.parse_args()
    raise SystemExit(serve(project_root=args.project_root, app_data_root_path=args.app_data_root))


if __name__ == "__main__":
    main()
