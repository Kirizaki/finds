# finds - Copyright (c) 2026 Kirizaki

import multiprocessing as mp
import threading


def production_lock_factory(name: str):
    if name == "counter":
        return threading.Lock()
    elif name in ["quota", "metadata"]:
        return mp.Lock()

    raise NotImplementedError("Not yet :(")

