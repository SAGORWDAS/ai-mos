"""Disposable extraction worker. No provider credentials are inherited by its parent call."""

import ctypes
import json
import sys


def limits():
    if sys.platform == "win32":
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [
                ("user_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t),
                ("active_processes", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in [
                    "read_ops",
                    "write_ops",
                    "other_ops",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                ]
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        handle = kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x100
        info.process_memory = 512 * 1024 * 1024
        if (
            not handle
            or not kernel.SetInformationJobObject(
                handle, 9, ctypes.byref(info), ctypes.sizeof(info)
            )
            or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())
        ):
            raise RuntimeError("resource_limit_unavailable")
        return handle
    else:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        return None


def main():
    guard = limits()
    from fastapi import HTTPException

    from app.growth.ingestion import pdf_text

    body = sys.stdin.buffer.read(5_000_001)
    if len(body) > 5_000_000:
        print(json.dumps({"error": "pdf_limit_5mb"}))
        return
    try:
        result = pdf_text(body)
        print(json.dumps({"text": result}))
    except HTTPException as error:
        print(json.dumps({"error": str(error.detail)}))
    _ = guard


if __name__ == "__main__":
    main()
