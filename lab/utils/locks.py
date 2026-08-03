# finds - Copyright (c) 2026 Kirizaki

import threading
import multiprocessing as mp

def production_lock_factory(name: str):
    if name == "counter":
        return threading.Lock()
    elif name in ["quota", "metadata"]:
        return mp.Lock()

    raise NotImplementedError("Not yet :(")

