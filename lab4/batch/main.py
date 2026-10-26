import json
import multiprocessing as mp
import os
import signal
import time


def cpu_load(stop):
    value = 1
    while not stop.is_set():
        for _ in range(10_000):
            value = (value * 1664525 + 1013904223) % 4294967296


def main():
    workers = int(os.getenv("CPU_WORKERS", "1"))
    memory_mib = int(os.getenv("MEMORY_MIB", "64"))

    if workers < 0 or memory_mib < 0:
        raise ValueError("CPU_WORKERS and MEMORY_MIB must be nonnegative")

    stop = mp.Event()

    def shutdown(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Touch every page so memory is actually used, not merely reserved.
    memory = bytearray(memory_mib * 1024 * 1024)
    for offset in range(0, len(memory), 4096):
        memory[offset] = 1

    processes = []
    try:
        for _ in range(workers):
            process = mp.Process(target=cpu_load, args=(stop,))
            process.start()
            processes.append(process)

        print(json.dumps({
            "message": "Batch workload started",
            "cpu_workers": workers,
            "memory_mib": memory_mib,
        }), flush=True)

        while not stop.wait(10):
            print(json.dumps({
                "message": "Batch workload running",
                "timestamp": time.time(),
                "cpu_workers_alive": sum(p.is_alive() for p in processes),
                "allocated_bytes": len(memory),
            }), flush=True)
    finally:
        stop.set()
        for process in processes:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join()


if __name__ == "__main__":
    main()
