# finds - Copyright (c) 2026 Kirizaki

import threading

def production_thread_factory(target, args=()):
    return threading.Thread(target=target, args=args)

